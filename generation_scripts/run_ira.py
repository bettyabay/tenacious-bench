"""
run_ira.py — Intra-Rater Agreement sampler for Tenacious-Bench v0.1

Samples 30 pairs (3 per probe × 10 probes, difficulty-stratified) and prints
them to the console so you can record your labels manually.

Run this twice, 24 hours apart, without looking at your first labels.
Compare the two label sets to compute intra-rater agreement.

Usage:
    python generation_scripts/run_ira.py
    python generation_scripts/run_ira.py --session 2   # for your second pass
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT_FILES = [
    REPO_ROOT / "tenacious_bench_v0.1" / "train"    / "pairs.jsonl",
    REPO_ROOT / "tenacious_bench_v0.1" / "dev"      / "pairs.jsonl",
    REPO_ROOT / "tenacious_bench_v0.1" / "held_out" / "pairs.jsonl",
]
SAMPLE_FILE = Path(__file__).resolve().parent / "ira_sample.jsonl"
SEED        = 42
PAIRS_PER_PROBE = 3
DIFFICULTIES    = ["easy", "medium", "hard"]
TRUNC = 200


def load_all_pairs() -> list[dict]:
    pairs = []
    for path in SPLIT_FILES:
        if not path.exists():
            print(f"[WARN] not found: {path}")
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    pairs.append(json.loads(line))
    return pairs


def sample_pairs(pairs: list[dict]) -> list[dict]:
    rng = random.Random(SEED)

    by_probe_diff: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for p in pairs:
        by_probe_diff[p["probe_id"]][p.get("difficulty", "unknown")].append(p)

    sampled = []
    for probe in sorted(by_probe_diff):
        buckets   = by_probe_diff[probe]
        selected  = []

        # One from each difficulty tier (where available)
        for diff in DIFFICULTIES:
            if len(selected) < PAIRS_PER_PROBE and buckets.get(diff):
                selected.append(rng.choice(buckets[diff]))

        # Fill remaining slots from whatever is left
        pool = [p for diff in DIFFICULTIES for p in buckets.get(diff, []) if p not in selected]
        while len(selected) < PAIRS_PER_PROBE and pool:
            pick = rng.choice(pool)
            selected.append(pick)
            pool.remove(pick)

        sampled.extend(selected)

    return sampled


def trunc(text: str) -> str:
    text = (text or "").strip()
    return text[:TRUNC] + "…" if len(text) > TRUNC else text


def print_pair(n: int, pair: dict) -> None:
    ctx      = pair.get("context", {})
    chosen   = pair.get("chosen",  {})
    rejected = pair.get("rejected", {})

    print(f"\n{'─' * 68}")
    print(f"[{n:02d}/30]  pair_id   : {pair['pair_id']}")
    print(f"        probe_id  : {pair['probe_id']}")
    print(f"        difficulty: {pair.get('difficulty', '?')}   mode: {pair.get('authoring_mode', '?')}")
    print()
    print(f"  CONTEXT")
    print(f"    company       : {ctx.get('company', 'N/A')}")
    print(f"    headcount     : {ctx.get('headcount', 'N/A')}")
    print(f"    disqualifiers : {ctx.get('disqualifiers', [])}")
    print(f"    recipient_role: {ctx.get('recipient_role', 'N/A')}")
    print()
    print(f"  CHOSEN  (action={chosen.get('action', '?')})")
    print(f"    {trunc(chosen.get('output', '(empty)'))}")
    print()
    print(f"  REJECTED (action={rejected.get('action', '?')})")
    print(f"    {trunc(rejected.get('output', '(empty)'))}")
    print()
    print(f"  Your label  →  1 = chosen is correct   0 = chosen is wrong   ? = skip")
    print(f"  Label: ___")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=int, default=1,
                        help="Label session number (1 = first pass, 2 = second pass 24h later)")
    args = parser.parse_args()

    print("Loading pairs…")
    all_pairs = load_all_pairs()
    print(f"  {len(all_pairs)} pairs loaded from all splits")

    sampled = sample_pairs(all_pairs)
    probes  = sorted({p["probe_id"] for p in sampled})
    print(f"  {len(sampled)} pairs sampled across {len(probes)} probes")
    print(f"  Probes: {probes}")

    # Save the sample once (session 1) so the same pairs are used in session 2
    if args.session == 1:
        with open(SAMPLE_FILE, "w", encoding="utf-8") as fh:
            for p in sampled:
                fh.write(json.dumps(p) + "\n")
        print(f"  Sample saved → {SAMPLE_FILE}")
    else:
        if SAMPLE_FILE.exists():
            with open(SAMPLE_FILE, encoding="utf-8") as fh:
                sampled = [json.loads(l) for l in fh if l.strip()]
            print(f"  Loaded existing sample from {SAMPLE_FILE}")
        else:
            print("[WARN] ira_sample.jsonl not found — using freshly sampled pairs")

    print(f"\n{'═' * 68}")
    print(f"  INTRA-RATER AGREEMENT — SESSION {args.session}")
    print(f"  Instructions:")
    print(f"    For each pair, decide: is CHOSEN the correct action?")
    print(f"    Write 1 (yes), 0 (no), or ? (unsure) next to 'Label:'")
    print(f"    Work through all 30. Do NOT look at session-1 labels for session 2.")
    print(f"{'═' * 68}")

    for i, pair in enumerate(sampled):
        print_pair(i + 1, pair)

    print(f"\n{'═' * 68}")
    print(f"  Done. Transfer your 30 labels to:")
    print(f"  generation_scripts/ira_labels_session{args.session}.txt")
    print(f"  Format: one label per line (1 / 0 / ?), in the same order as above.")
    print(f"{'═' * 68}\n")


if __name__ == "__main__":
    main()
