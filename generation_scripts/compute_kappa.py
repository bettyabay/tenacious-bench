"""
compute_kappa.py — Intra-rater agreement calculator for Tenacious-Bench IRA

Usage:
    python generation_scripts/compute_kappa.py

Expects:
    generation_scripts/ira_labels_session1.txt  (one label per line: 1, 0, or ?)
    generation_scripts/ira_labels_session2.txt  (same format, same order)
"""

from pathlib import Path

LABELS_DIR = Path(__file__).resolve().parent
SESSION1   = LABELS_DIR / "ira_labels_session1.txt"
SESSION2   = LABELS_DIR / "ira_labels_session2.txt"
SAMPLE     = LABELS_DIR / "ira_sample.jsonl"
KAPPA_THRESHOLD = 0.80


def load_labels(path: Path) -> list:
    labels = []
    with open(path, encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text not in {"0", "1", "?"}:
                raise ValueError(
                    f"Invalid label on line {line_num} in {path.name}: {text!r}. "
                    "Expected 1, 0, or ? (or comment lines starting with #)."
                )
            labels.append(text)
    return labels


def cohen_kappa(labels1: list[int], labels2: list[int]) -> float:
    n = len(labels1)
    if n == 0:
        return 0.0
    po = sum(a == b for a, b in zip(labels1, labels2)) / n
    p1 = sum(labels1) / n
    p2 = sum(labels2) / n
    pe = (p1 * p2) + ((1 - p1) * (1 - p2))
    return 1.0 if pe == 1.0 else (po - pe) / (1 - pe)


def main() -> None:
    for path in (SESSION1, SESSION2):
        if not path.exists():
            print(f"[ERROR] Missing label file: {path}")
            print("        Create the file with one label per line (1, 0, or ?).")
            return

    raw1 = load_labels(SESSION1)
    raw2 = load_labels(SESSION2)

    if len(raw1) != len(raw2):
        print(f"[ERROR] Session 1 has {len(raw1)} labels, Session 2 has {len(raw2)}.")
        print("        Both files must have the same number of lines.")
        return

    # Load pair metadata for disagreement reporting
    pairs = []
    if SAMPLE.exists():
        import json
        with open(SAMPLE, encoding="utf-8") as fh:
            pairs = [json.loads(l) for l in fh if l.strip()]

    # Filter skipped pairs
    valid, skipped = [], []
    for i, (a, b) in enumerate(zip(raw1, raw2)):
        if a == "?" or b == "?":
            skipped.append(i + 1)
        else:
            valid.append((i + 1, int(a), int(b)))

    labels1 = [v[1] for v in valid]
    labels2 = [v[2] for v in valid]

    agreements    = sum(a == b for a, b in zip(labels1, labels2))
    disagreements = len(valid) - agreements
    kappa         = cohen_kappa(labels1, labels2)
    passed        = kappa >= KAPPA_THRESHOLD

    print(f"\n{'═' * 55}")
    print(f"  INTRA-RATER AGREEMENT RESULTS")
    print(f"{'═' * 55}")
    print(f"  Total pairs      : {len(raw1)}")
    print(f"  Skipped (?)      : {len(skipped)}")
    print(f"  Pairs compared   : {len(valid)}")
    print(f"  Agreements       : {agreements}")
    print(f"  Disagreements    : {disagreements}")
    print(f"  Raw agreement    : {agreements / len(valid):.1%}")
    print(f"  Cohen's kappa    : {kappa:.4f}")
    print(f"  Threshold        : {KAPPA_THRESHOLD}")
    print(f"  Status           : {'✓ PASS' if passed else '✗ FAIL — revise rubric'}")
    print(f"{'═' * 55}")

    if disagreements > 0:
        print(f"\n  Disagreements:")
        for row_num, s1, s2 in valid:
            if s1 != s2:
                meta = pairs[row_num - 1] if row_num - 1 < len(pairs) else {}
                pair_id   = meta.get("pair_id",   "unknown")
                probe_id  = meta.get("probe_id",  "unknown")
                difficulty = meta.get("difficulty", "?")
                print(f"    row {row_num:02d}  {pair_id:35s}  probe={probe_id}  diff={difficulty}")
                print(f"           session1={s1}  session2={s2}")

    if not passed:
        print(f"\n  [ACTION] kappa {kappa:.4f} < {KAPPA_THRESHOLD}.")
        print("  → Review the disagreed pairs above.")
        print("  → Clarify the ambiguous rationale fields in those pairs.")
        print("  → Re-label and rerun until kappa ≥ 0.80.")
    else:
        print(f"\n  Rubric is consistent. Proceed to ORPO training.")

    print()


if __name__ == "__main__":
    main()
