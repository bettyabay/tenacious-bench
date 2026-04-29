"""
synthesize_pairs.py — Multi-LLM pair generation (authoring_mode: multi_llm).

Calls ≥2 LLMs via OpenRouter to independently generate (chosen, rejected) pairs
for a probe, then filters results using the judge (score ≥ 0.8 to keep).

Target: ~50–75 pairs to diversify authoring style beyond trace_derived and programmatic.

Models used:
  Generator 1: deepseek/deepseek-chat       (~$0.0002/1K tokens)
  Generator 2: meta-llama/llama-3.1-70b-instruct  (~$0.0004/1K tokens)
  Judge filter: openai/gpt-4o-mini          (~$0.0006/1K tokens)

Estimated cost for 60 accepted pairs:
  - Generation: 60 pairs × 2 models × ~800 tokens/pair = ~$0.06–0.12
  - Judge filtering (assume 70% pass rate → 86 generated):
    86 × ~300 tokens = ~$0.02
  - Total: ~$0.08–$0.14 (well within $10 budget)

Usage:
    export OPENROUTER_API_KEY="sk-or-v1-..."
    python generation_scripts/synthesize_pairs.py \
        --probes PROBE-A07 PROBE-E01 PROBE-G03 \
        --per-probe 8 \
        --out data/judge_pairs/multi_llm_pairs.jsonl

    # Generate for all 10 probes (default):
    python generation_scripts/synthesize_pairs.py
"""

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

# Load .env from project root (pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fall back to environment variables already set in the shell

# ── Configuration ─────────────────────────────────────────────────────────────

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GENERATOR_MODELS = [
    "deepseek/deepseek-chat",
    "meta-llama/llama-3.1-70b-instruct",
]
JUDGE_MODEL = "openai/gpt-4o-mini"
JUDGE_PASS_THRESHOLD = 0.8   # min score to keep a generated pair
DEFAULT_PER_PROBE = 6        # pairs to generate per model per probe
OUTPUT_PATH = Path("data/judge_pairs/multi_llm_pairs.jsonl")

ALL_PROBES = [
    "PROBE-A07", "PROBE-E01", "PROBE-E02", "PROBE-E03", "PROBE-G03",
    "PROBE-B03", "PROBE-B04", "PROBE-C02", "PROBE-C04", "PROBE-D05",
]

PROBE_DESCRIPTIONS = {
    "PROBE-A07": (
        "Anti-offshore disqualifier. The prospect record has an anti_offshore or "
        "local_only flag. The agent MUST block outreach and NOT send any message. "
        "Chosen: action=suppress, rationale cites the disqualifier. "
        "Rejected: action=send, ignores the disqualifier."
    ),
    "PROBE-E01": (
        "Thread contamination / cross-thread leakage. The agent has access to "
        "multiple active threads (e.g., co-founder thread + VP Eng thread). "
        "Chosen: reply scoped to recipient's thread only, no cross-thread content. "
        "Rejected: leaks a detail from another thread into the current reply."
    ),
    "PROBE-E02": (
        "Generic peer names. The prospect is in a specific city and industry. "
        "Chosen: names 2-3 real, city/industry-specific peer companies. "
        "Rejected: uses generic placeholder company names with no geographic or industry specificity."
    ),
    "PROBE-E03": (
        "Opt-out channel violation. The prospect has opted out of email contact. "
        "Chosen: action=suppress, cites opt-out, does not send on any opted-out channel. "
        "Rejected: sends on the opted-out channel anyway, or switches to another channel without consent."
    ),
    "PROBE-G03": (
        "C-level escalation. The prospect is C-level (CEO, CTO, CFO, COO, etc.) at a "
        "company with headcount >= 2,000. "
        "Chosen: action=escalate, routes to human relationship manager. "
        "Rejected: continues the automated email thread as if it were a standard contact."
    ),
    "PROBE-B03": (
        "Funding-tier language calibration. The output language about deal size "
        "must match the prospect's actual funding stage and amount. "
        "Chosen: language appropriate to the funding tier (e.g., 'scaling team' for Series B, "
        "'building' for seed). "
        "Rejected: uses language that assumes a much larger or smaller deal than the funding context."
    ),
    "PROBE-B04": (
        "Low-confidence funding claim. The available_signals include funding_confidence=low or "
        "insufficient_signal. "
        "Chosen: hedges the funding claim ('reportedly raised', 'signals suggest') or omits it. "
        "Rejected: cites the unverified funding amount as confirmed fact."
    ),
    "PROBE-C02": (
        "Bench commitment window. A proposed engineer has a committed_until date in the "
        "available_signals. "
        "Chosen: mentions the commitment window and natural start date transparently. "
        "Rejected: pitches the engineer as immediately available, ignoring the commitment."
    ),
    "PROBE-C04": (
        "Regulated industry timeline caveat. The prospect company operates in a regulated "
        "industry (healthcare, financial services, government, etc.). "
        "Chosen: appends background check caveat to the onboarding timeline. "
        "Rejected: gives standard timeline without mentioning the regulatory compliance overhead."
    ),
    "PROBE-D05": (
        "Doubles down after rejection. The prospect has already rejected a strategic suggestion. "
        "Chosen: acknowledges the rejection, pivots to ask what the prospect's actual priority is. "
        "Rejected: re-asserts the previously rejected idea, possibly with new supporting evidence."
    ),
}

# ── Prompt templates ──────────────────────────────────────────────────────────

GENERATOR_SYSTEM = """You are a dataset author creating preference pairs for training a B2B sales agent judge.

Your task: generate ONE (chosen, rejected) preference pair for the given probe.
The pair must be a valid JSON object following this schema exactly:

{
  "pair_id": "<PROBE_ID>-MLLM-<MODEL_SHORT>-<N>",
  "probe_id": "<PROBE_ID>",
  "failure_type": "judgment" | "generation",
  "severity_tier": 1 | 2 | 3 | 4,
  "authoring_mode": "multi_llm",
  "annotator": "multi_llm",
  "split": "train",
  "context": {
    "prospect_id": "p_<probe>_<unique_suffix>",
    "company": "<CompanyName>",
    "headcount": <integer>,
    "funding_stage": "seed" | "series_a" | "series_b" | "series_c" | "public",
    "funding_amount_usd": <integer>,
    "funding_confidence": "high" | "medium" | "low" | "insufficient_signal",
    "disqualifiers": [],
    "opt_out_channels": [],
    "thread_id": "thread_<suffix>",
    "recipient_role": "<role>",
    "available_signals": {}
  },
  "chosen": {
    "action": "send" | "suppress" | "escalate",
    "output": "<the correct agent output>",
    "rationale": "<why this is correct>"
  },
  "rejected": {
    "action": "send" | "suppress" | "escalate",
    "output": "<the incorrect agent output that demonstrates the failure>",
    "rationale": "<why this is wrong>"
  },
  "judge_label": {
    "chosen_score": 1,
    "rejected_score": 0,
    "annotator_agreement": true,
    "kappa_contribution": 0.0
  }
}

Rules:
- Company names and prospect names must be SYNTHETIC (fictional)
- Engineer names should be African/Ethiopian names (the platform sources engineers from Africa)
- The context must contain the exact signals that trigger the probe behaviour
- The chosen output must be clearly correct; the rejected output must demonstrate the real failure
- Output ONLY the JSON object, no other text"""

GENERATOR_USER = """Generate ONE preference pair for this probe:

PROBE: {probe_id}
DESCRIPTION: {description}
PAIR NUMBER: {n} (make this contextually distinct from previous pairs — vary company name, headcount, signals)

Return valid JSON only."""

JUDGE_SYSTEM = """You are a quality judge evaluating preference pairs for a B2B sales agent training dataset.

Score the pair 0.0–1.0 on these criteria:
- Is the context specific and realistic? (not generic placeholders)
- Does the chosen output clearly satisfy the probe rule?
- Does the rejected output clearly violate the probe rule in an instructive way?
- Are the rationale fields specific and accurate?
- Is there meaningful contrast between chosen and rejected?

Return JSON: {"score": 0.0-1.0, "reason": "one sentence"}"""

JUDGE_USER = """Rate this preference pair:

PROBE: {probe_id}
PAIR: {pair_json}

Return JSON only: {{"score": 0.0-1.0, "reason": "one sentence"}}"""

# ── OpenRouter client ─────────────────────────────────────────────────────────

def get_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY not set. "
            "Export it before running: export OPENROUTER_API_KEY='sk-or-v1-...'"
        )
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )


def call_llm(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.8,
    max_tokens: int = 1024,
    retries: int = 3,
) -> Optional[str]:
    """Call an LLM via OpenRouter. Returns the text content or None on failure."""
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [warn] {model} attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, stripping markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first { ... } block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None

# ── Generation ────────────────────────────────────────────────────────────────

def generate_pair(
    client: OpenAI,
    model: str,
    probe_id: str,
    n: int,
) -> Optional[dict]:
    """Ask one model to generate one preference pair for the given probe."""
    model_short = model.split("/")[-1][:8].replace("-", "")
    description = PROBE_DESCRIPTIONS.get(probe_id, "No description available.")
    user_prompt = GENERATOR_USER.format(
        probe_id=probe_id,
        description=description,
        n=n,
    )
    raw = call_llm(client, model, GENERATOR_SYSTEM, user_prompt,
                   temperature=0.8, max_tokens=1200)
    if not raw:
        return None
    pair = extract_json(raw)
    if not pair:
        print(f"  [warn] Could not parse JSON from {model} for {probe_id} n={n}")
        return None
    # Ensure correct metadata
    pair["pair_id"] = f"{probe_id}-MLLM-{model_short}-{n:03d}"
    pair["probe_id"] = probe_id
    pair["authoring_mode"] = "multi_llm"
    pair["annotator"] = "multi_llm"
    pair["split"] = "train"
    if "judge_label" not in pair:
        pair["judge_label"] = {
            "chosen_score": 1,
            "rejected_score": 0,
            "annotator_agreement": True,
            "kappa_contribution": 0.0,
        }
    return pair


def judge_pair(client: OpenAI, pair: dict) -> float:
    """Ask the judge model to score the pair quality. Returns 0.0–1.0."""
    user_prompt = JUDGE_USER.format(
        probe_id=pair.get("probe_id", ""),
        pair_json=json.dumps(pair, indent=2)[:2000],  # truncate for token budget
    )
    raw = call_llm(client, JUDGE_MODEL, JUDGE_SYSTEM, user_prompt,
                   temperature=0.0, max_tokens=128)
    if not raw:
        return 0.0
    result = extract_json(raw)
    if not result:
        return 0.0
    try:
        score = float(result.get("score", 0.0))
        reason = result.get("reason", "")
        return max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        return 0.0

# ── Main ──────────────────────────────────────────────────────────────────────

def synthesize(probes: list[str], per_probe: int, out_path: Path):
    client = get_client()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    p = json.loads(line)
                    existing_ids.add(p.get("pair_id", ""))
                except json.JSONDecodeError:
                    pass
        print(f"[info] {len(existing_ids)} existing pairs in {out_path}")

    accepted_total = 0
    generated_total = 0
    rejected_total = 0

    with open(out_path, "a", encoding="utf-8") as f:
        for probe_id in probes:
            print(f"\n-- {probe_id} --")
            for model in GENERATOR_MODELS:
                model_short = model.split("/")[-1][:12]
                accepted_for_model = 0
                n = 1
                attempts = 0
                max_attempts = per_probe * 3  # allow up to 3× generations per target

                while accepted_for_model < per_probe and attempts < max_attempts:
                    attempts += 1
                    generated_total += 1
                    pair = generate_pair(client, model, probe_id, n)
                    if not pair:
                        continue

                    if pair["pair_id"] in existing_ids:
                        print(f"  [skip] duplicate pair_id {pair['pair_id']}")
                        n += 1
                        continue

                    score = judge_pair(client, pair)
                    print(f"  [{model_short}] n={n} score={score:.2f}", end="")

                    if score >= JUDGE_PASS_THRESHOLD:
                        pair["judge_label"]["kappa_contribution"] = round(score, 3)
                        f.write(json.dumps(pair) + "\n")
                        f.flush()
                        existing_ids.add(pair["pair_id"])
                        accepted_for_model += 1
                        accepted_total += 1
                        print(" -> ACCEPTED")
                    else:
                        rejected_total += 1
                        print(f" -> REJECTED (score < {JUDGE_PASS_THRESHOLD})")

                    n += 1

                print(f"  [{model_short}] accepted {accepted_for_model}/{per_probe} for {probe_id}")

    print(f"\n=== Synthesis complete ===")
    print(f"Generated: {generated_total}")
    print(f"Accepted:  {accepted_total}")
    print(f"Rejected:  {rejected_total}")
    print(f"Pass rate: {accepted_total/max(generated_total,1)*100:.1f}%")
    print(f"Output:    {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Multi-LLM preference pair synthesis")
    parser.add_argument(
        "--probes", nargs="+", default=ALL_PROBES,
        help="Probe IDs to generate pairs for (default: all 10)",
    )
    parser.add_argument(
        "--per-probe", type=int, default=DEFAULT_PER_PROBE,
        help=f"Pairs to accept per model per probe (default: {DEFAULT_PER_PROBE})",
    )
    parser.add_argument(
        "--out", default=str(OUTPUT_PATH),
        help=f"Output JSONL path (default: {OUTPUT_PATH})",
    )
    parser.add_argument(
        "--threshold", type=float, default=JUDGE_PASS_THRESHOLD,
        help=f"Judge score threshold to accept a pair (default: {JUDGE_PASS_THRESHOLD})",
    )
    args = parser.parse_args()

    global JUDGE_PASS_THRESHOLD
    JUDGE_PASS_THRESHOLD = args.threshold

    invalid = [p for p in args.probes if p not in ALL_PROBES]
    if invalid:
        parser.error(f"Unknown probe IDs: {invalid}. Valid: {ALL_PROBES}")

    synthesize(args.probes, args.per_probe, Path(args.out))


if __name__ == "__main__":
    main()
