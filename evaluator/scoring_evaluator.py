"""
scoring_evaluator.py — Path B judge inference wrapper

Scores a Conversion Engine output before dispatch.
Returns a JudgeVerdict with a score, recommended action, and reason.
Blocks outputs that fall below the configured threshold.

Usage:
    python scoring_evaluator.py --context context.json --output draft.txt
"""

import argparse
import json
import os
import sys

# Load .env from project root (pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from dataclasses import dataclass, asdict
from typing import Literal

import openai  # OpenRouter is OpenAI-compatible

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
JUDGE_MODEL = "openai/gpt-4o-mini"          # dev-tier — cheap
BLOCK_THRESHOLD = 0.5                        # scores below this are blocked
MAX_TOKENS = 512

SYSTEM_PROMPT = """You are a sales-outreach judge for a B2B software company.
Your job is to evaluate whether a drafted agent output should be sent as-is,
regenerated, escalated to a human, or suppressed entirely.

You will be given:
- context: structured data the agent had access to (prospect info, signals, disqualifiers)
- draft_output: the text the agent wants to send

Evaluate the draft against these rules (in priority order):
1. SUPPRESS if any disqualifier is present in context.disqualifiers (e.g. anti_offshore).
2. SUPPRESS if the prospect is in context.opt_out_channels for the intended channel.
3. ESCALATE if recipient_role is c_level AND headcount > 2000.
4. BLOCK (score 0) if the draft leaks content from a different thread_id.
5. BLOCK (score 0) if a funding amount is cited but funding_confidence is low or insufficient_signal.
6. PENALISE (score 0.3) if peer company names appear generic or reused across prospects.
7. PASS (score 1.0) if none of the above conditions are triggered.

Respond with valid JSON only. No explanation outside the JSON object.

Response format:
{
  "score": <float 0.0–1.0>,
  "action": "suppress" | "escalate" | "regenerate" | "send",
  "triggered_rule": "<short label of the rule that was triggered, or null>",
  "reason": "<one sentence explaining the verdict>"
}"""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class JudgeVerdict:
    score: float
    action: Literal["suppress", "escalate", "regenerate", "send"]
    triggered_rule: str | None
    reason: str
    blocked: bool

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Judge call
# ---------------------------------------------------------------------------

def call_judge(context: dict, draft_output: str) -> JudgeVerdict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY is not set.")

    client = openai.OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )

    user_message = json.dumps({
        "context": context,
        "draft_output": draft_output,
    }, indent=2)

    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0.0,    # deterministic scoring
    )

    raw = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Judge returned non-JSON response: {raw}") from exc

    score = float(parsed["score"])
    action = parsed["action"]
    triggered_rule = parsed.get("triggered_rule")
    reason = parsed.get("reason", "")
    blocked = score < BLOCK_THRESHOLD

    # Overrides: suppress and escalate are always blocked regardless of score
    if action in ("suppress", "escalate"):
        blocked = True

    return JudgeVerdict(
        score=score,
        action=action,
        triggered_rule=triggered_rule,
        reason=reason,
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
# Batch evaluation over judge_pairs.jsonl (for measuring judge accuracy)
# ---------------------------------------------------------------------------

def evaluate_pairs(pairs_path: str) -> dict:
    correct = 0
    total = 0
    errors = []

    with open(pairs_path, encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            context = record["context"]

            # Score the rejected output — judge should block it
            rejected_output = record["rejected"]["output"]
            try:
                verdict = call_judge(context, rejected_output)
                if verdict.blocked:
                    correct += 1
                else:
                    errors.append({
                        "line": line_num,
                        "pair_id": record.get("pair_id"),
                        "probe_id": record.get("probe_id"),
                        "issue": "judge did not block rejected output",
                        "score": verdict.score,
                        "action": verdict.action,
                    })
            except Exception as exc:
                errors.append({
                    "line": line_num,
                    "pair_id": record.get("pair_id"),
                    "issue": str(exc),
                })

            total += 1

    accuracy = correct / total if total else 0.0
    return {
        "total_pairs": total,
        "correctly_blocked": correct,
        "accuracy": round(accuracy, 4),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a draft agent output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Single scoring
    score_parser = subparsers.add_parser("score", help="Score one draft output.")
    score_parser.add_argument("--context", required=True, help="Path to context JSON file.")
    score_parser.add_argument("--output", required=True, help="Path to draft output text file.")

    # Batch evaluation
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate judge accuracy over judge_pairs.jsonl.")
    eval_parser.add_argument("--pairs", required=True, help="Path to judge_pairs.jsonl.")
    eval_parser.add_argument("--out", default="eval_results.json", help="Output file for results.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "score":
        with open(args.context, encoding="utf-8") as fh:
            context = json.load(fh)
        with open(args.output, encoding="utf-8") as fh:
            draft_output = fh.read()

        verdict = call_judge(context, draft_output)
        print(json.dumps(verdict.to_dict(), indent=2))

        if verdict.blocked:
            print(f"\n[BLOCKED] action={verdict.action} | {verdict.reason}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"\n[PASSED] score={verdict.score:.2f} | {verdict.reason}", file=sys.stderr)

    elif args.command == "evaluate":
        results = evaluate_pairs(args.pairs)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(json.dumps(results, indent=2))
        print(f"\nAccuracy: {results['accuracy']:.2%} ({results['correctly_blocked']}/{results['total_pairs']})")


if __name__ == "__main__":
    main()
