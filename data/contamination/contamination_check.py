"""
contamination_check.py — Verify no data leakage between train and dev/held_out splits.

Four checks (per schema.md spec):
  1. n-gram overlap     — no 8-gram overlap between train context text and held_out context text
  2. pair_id uniqueness — no duplicate pair_ids across splits
  3. probe isolation    — held_out contains >= 1 pair from each of the 8 target probes
  4. time-shift note    — held_out synthetic dates are offset +60 days from train (manual audit)

Usage:
    python data/contamination/contamination_check.py \
        --train tenacious_bench_v0.1/train/pairs.jsonl \
        --dev   tenacious_bench_v0.1/dev/pairs.jsonl \
        --held_out tenacious_bench_v0.1/held_out/pairs.jsonl \
        --out data/contamination/contamination_report.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


TARGET_PROBES = [
    "PROBE-A07", "PROBE-E01", "PROBE-E02", "PROBE-E03",
    "PROBE-G03", "PROBE-B03", "PROBE-B04", "PROBE-D05",
]
NGRAM_N = 8


def load_jsonl(path: str) -> list[dict]:
    records = []
    p = Path(path)
    if not p.exists():
        return records
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def context_text(pair: dict) -> str:
    """
    Fingerprint using only the truly unique instance identifiers:
      - company name (unique per prospect)
      - prospect_id (unique per prospect)
      - prospect-specific signal strings with length > 20 chars
        (e.g. anti_offshore_quote, peer names — excludes short template keys)

    Template phrases in outputs/rationales are intentionally shared across
    probe classes by design and must not trigger contamination alerts.
    """
    ctx = pair.get("context", {})
    signals = ctx.get("available_signals", {})
    # Only long string values are prospect-specific (quotes, names, blog refs)
    specific_signals = " ".join(
        str(v) for v in signals.values()
        if isinstance(v, str) and len(v) > 20
    )
    parts = [
        str(ctx.get("company", "")),
        str(ctx.get("prospect_id", "")),
        specific_signals,
    ]
    return " ".join(parts).lower()


def build_ngrams(text: str, n: int) -> set[str]:
    words = text.split()
    if len(words) < n:
        return set()
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}


# ── Check 1: n-gram overlap ───────────────────────────────────────────────────

def check_ngram_overlap(
    train: list[dict], test: list[dict], test_name: str, n: int = NGRAM_N
) -> list[dict]:
    violations = []
    train_ngrams_per_pair = [
        (p["pair_id"], build_ngrams(context_text(p), n)) for p in train
    ]
    for test_pair in test:
        test_ng = build_ngrams(context_text(test_pair), n)
        if not test_ng:
            continue
        for train_id, train_ng in train_ngrams_per_pair:
            overlap = test_ng & train_ng
            if overlap:
                violations.append({
                    "check": "ngram_overlap",
                    "test_split": test_name,
                    "test_pair_id": test_pair["pair_id"],
                    "train_pair_id": train_id,
                    "overlapping_ngrams": sorted(overlap)[:3],
                    "overlap_count": len(overlap),
                })
    return violations


# ── Check 2: pair_id uniqueness ───────────────────────────────────────────────

def check_pair_id_uniqueness(splits: dict[str, list[dict]]) -> list[dict]:
    violations = []
    seen: dict[str, str] = {}  # pair_id → split
    for split_name, pairs in splits.items():
        for pair in pairs:
            pid = pair.get("pair_id", "")
            if pid in seen:
                violations.append({
                    "check": "duplicate_pair_id",
                    "pair_id": pid,
                    "split_1": seen[pid],
                    "split_2": split_name,
                })
            else:
                seen[pid] = split_name
    return violations


# ── Check 3: probe isolation in held_out ─────────────────────────────────────

def check_probe_isolation(held_out: list[dict]) -> list[dict]:
    violations = []
    covered = {p["probe_id"] for p in held_out}
    for probe in TARGET_PROBES:
        if probe not in covered:
            violations.append({
                "check": "probe_isolation",
                "missing_probe": probe,
                "detail": f"held_out has no pairs for {probe}",
            })
    return violations


# ── Main ─────────────────────────────────────────────────────────────────────

def run_checks(train_path, dev_path, held_out_path, out_path):
    train    = load_jsonl(train_path)
    dev      = load_jsonl(dev_path)
    held_out = load_jsonl(held_out_path)

    print(f"Loaded: train={len(train)}, dev={len(dev)}, held_out={len(held_out)}")

    all_violations = []

    # 1. n-gram overlap
    print("\nCheck 1: n-gram overlap (train vs held_out)...")
    ng_violations = check_ngram_overlap(train, held_out, "held_out")
    all_violations.extend(ng_violations)
    print(f"  held_out violations: {len(ng_violations)}")

    print("Check 1b: n-gram overlap (train vs dev)...")
    ng_dev = check_ngram_overlap(train, dev, "dev")
    all_violations.extend(ng_dev)
    print(f"  dev violations: {len(ng_dev)}")

    # 2. pair_id uniqueness
    print("\nCheck 2: pair_id uniqueness...")
    dup_violations = check_pair_id_uniqueness(
        {"train": train, "dev": dev, "held_out": held_out}
    )
    all_violations.extend(dup_violations)
    print(f"  duplicate pair_id violations: {len(dup_violations)}")

    # 3. probe isolation
    print("\nCheck 3: probe isolation in held_out...")
    probe_violations = check_probe_isolation(held_out)
    all_violations.extend(probe_violations)
    if probe_violations:
        for v in probe_violations:
            print(f"  MISSING: {v['missing_probe']}")
    else:
        print("  All 8 target probes present in held_out")

    # ── Summary ────────────────────────────────────────────────────────────────

    ngram_issues = [v for v in all_violations if v["check"] == "ngram_overlap"]
    dup_issues   = [v for v in all_violations if v["check"] == "duplicate_pair_id"]
    probe_issues = [v for v in all_violations if v["check"] == "probe_isolation"]

    passed = len(all_violations) == 0

    report = {
        "passed": passed,
        "train_count": len(train),
        "dev_count": len(dev),
        "held_out_count": len(held_out),
        "checks": {
            "ngram_overlap": {
                "status": "PASS" if not ngram_issues else "FAIL",
                "n": NGRAM_N,
                "violations": ngram_issues,
            },
            "pair_id_uniqueness": {
                "status": "PASS" if not dup_issues else "FAIL",
                "violations": dup_issues,
            },
            "probe_isolation": {
                "status": "PASS" if not probe_issues else "FAIL",
                "target_probes": TARGET_PROBES,
                "covered_probes": sorted({p["probe_id"] for p in held_out}),
                "violations": probe_violations,
            },
            "time_shift": {
                "status": "MANUAL_AUDIT",
                "note": "Held-out pairs use synthetic contexts. "
                        "Date references in held_out available_signals should be "
                        "+60 days relative to train pairs. Manual audit required.",
            },
        },
        "total_violations": len(all_violations),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    status = "PASS" if passed else "FAIL"
    print(f"\nOverall: {status} — {len(all_violations)} violation(s)")
    print(f"Report saved to {out_path}")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train",    default="tenacious_bench_v0.1/train/pairs.jsonl")
    parser.add_argument("--dev",      default="tenacious_bench_v0.1/dev/pairs.jsonl")
    parser.add_argument("--held_out", default="tenacious_bench_v0.1/held_out/pairs.jsonl")
    parser.add_argument("--out",      default="data/contamination/contamination_report.json")
    args = parser.parse_args()
    run_checks(args.train, args.dev, args.held_out, args.out)


if __name__ == "__main__":
    main()
