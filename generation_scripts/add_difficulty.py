"""
add_difficulty.py — Add difficulty_stratification field to all preference pairs.

Assigns one of three difficulty levels to each pair:

  easy   — Single rule, explicit signal, deterministic answer
             Examples: PROBE-A07 (disqualifier flag present), PROBE-E03 (opt-out channel set)

  medium — Boundary condition OR two conditions must both be true OR moderate signal reading
             Examples: PROBE-G03 (headcount > 2000 AND c_level), PROBE-B04 (check confidence level)

  hard   — Subtle judgment, compound rules, ambiguous signals, or adversarial edge cases
             Examples: PROBE-E01 (subtle thread leak), PROBE-D05 (soft rejection),
                       hand_authored compound (3 rules firing simultaneously)

Classification logic (in priority order):
  1. Probe-based base difficulty
  2. hand_authored + compound signals (2+ rules) → override to hard
  3. hand_authored + 1 rule on easy probe → bump to medium
  4. PROBE-G03 with headcount==2000 (exact boundary) → hard

Modifies files in-place:
  - data/judge_pairs/*.jsonl
  - tenacious_bench_v0.1/{train,dev,held_out}/pairs.jsonl

Also updates tenacious_bench_v0.1/dataset_stats.json with difficulty_stratification summary.

Usage:
    python generation_scripts/add_difficulty.py
"""

import json
from collections import defaultdict
from pathlib import Path

# ── Difficulty classification ─────────────────────────────────────────────────

# Probe base difficulty
PROBE_DIFFICULTY = {
    # Easy: single explicit rule fires, signal is a direct field value
    "PROBE-A07": "easy",    # disqualifiers list contains flag → Rule 1
    "PROBE-E03": "easy",    # opt_out_channels contains channel → Rule 2

    # Medium: boundary condition, two conditions, or moderate signal reading
    "PROBE-G03": "medium",  # headcount > 2000 AND c_level → two conditions (Rule 3)
    "PROBE-B03": "medium",  # funding tier language → cross-reference amount + stage
    "PROBE-B04": "medium",  # funding_confidence field → check enum value (Rule 5)
    "PROBE-C02": "medium",  # bench commitment in available_signals → read nested field
    "PROBE-C04": "medium",  # regulated industry → requires knowing industry taxonomy

    # Hard: subtle signals, ambiguous judgment, or relative comparison required
    "PROBE-E01": "hard",    # thread context leak → requires isolation check (subtle)
    "PROBE-E02": "hard",    # generic vs specific peers → subjective threshold (Rule 6)
    "PROBE-D05": "hard",    # soft rejection → ambiguous signal, nuanced pivot vs double-down
}

DEFAULT_DIFFICULTY = "medium"  # for probes not in the map


def assign_difficulty(pair: dict) -> str:
    """
    Assign difficulty label to a single preference pair.

    Returns: "easy" | "medium" | "hard"
    """
    probe_id       = pair.get("probe_id", "")
    authoring_mode = pair.get("authoring_mode", "")
    context        = pair.get("context", {})

    # Step 1 — base difficulty from probe type
    base = PROBE_DIFFICULTY.get(probe_id, DEFAULT_DIFFICULTY)

    # Step 2 — PROBE-G03 exact boundary (headcount == 2000) → hard
    # The rule fires at > 2000, so exactly 2000 is the hardest boundary case
    if probe_id == "PROBE-G03":
        headcount = context.get("headcount", 0)
        if headcount == 2000:
            base = "hard"

    # Step 3 — hand_authored compound cases
    # Count how many distinct rules could fire simultaneously
    if authoring_mode == "hand_authored":
        disqualifiers = context.get("disqualifiers", [])
        opt_out       = context.get("opt_out_channels", [])
        headcount     = context.get("headcount", 0)
        role          = context.get("recipient_role", "")
        funding_conf  = context.get("funding_confidence", "high")

        rules_potentially_firing = 0
        if disqualifiers:                                        # Rule 1
            rules_potentially_firing += 1
        if opt_out:                                              # Rule 2
            rules_potentially_firing += 1
        if headcount > 2000 and role == "c_level":              # Rule 3
            rules_potentially_firing += 1
        if funding_conf in ("low", "insufficient_signal"):       # Rule 5
            rules_potentially_firing += 1

        if rules_potentially_firing >= 2:
            base = "hard"          # compound → always hard
        elif rules_potentially_firing == 1 and base == "easy":
            base = "medium"        # single rule but hand-crafted edge case → medium

    return base


# ── File processing ───────────────────────────────────────────────────────────

TARGET_FILES = [
    # Raw source files
    "data/judge_pairs/trace_derived_pairs.jsonl",
    "data/judge_pairs/programmatic_pairs.jsonl",
    "data/judge_pairs/hand_authored_pairs.jsonl",
    "data/judge_pairs/multi_llm_pairs.jsonl",
    # Published split files
    "tenacious_bench_v0.1/train/pairs.jsonl",
    "tenacious_bench_v0.1/dev/pairs.jsonl",
    "tenacious_bench_v0.1/held_out/pairs.jsonl",
]

difficulty_counts = defaultdict(int)      # overall counts
per_probe_diff    = defaultdict(lambda: defaultdict(int))
pair_ids_by_diff  = defaultdict(list)     # for dataset_stats.json summary

total_updated = 0

for rel_path in TARGET_FILES:
    p = Path(rel_path)
    if not p.exists():
        print(f"  [skip] {rel_path} not found")
        continue

    lines_in  = p.read_text(encoding="utf-8").splitlines()
    lines_out = []
    file_count = 0

    for line in lines_in:
        line = line.strip()
        if not line:
            continue
        pair = json.loads(line)

        # Assign and stamp
        difficulty = assign_difficulty(pair)
        pair["difficulty"] = difficulty

        # Track stats (only for split files to avoid double-counting)
        if "tenacious_bench_v0.1" in rel_path:
            difficulty_counts[difficulty] += 1
            per_probe_diff[pair.get("probe_id", "unknown")][difficulty] += 1
            pair_ids_by_diff[difficulty].append(pair.get("pair_id", ""))

        lines_out.append(json.dumps(pair))
        file_count += 1

    p.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"  [done] {rel_path}: {file_count} pairs updated")
    total_updated += file_count

print(f"\nTotal pairs stamped: {total_updated}")
print(f"\nDifficulty distribution (split files):")
for d in ("easy", "medium", "hard"):
    print(f"  {d:6s}: {difficulty_counts[d]}")

# ── Update dataset_stats.json ─────────────────────────────────────────────────

stats_path = Path("tenacious_bench_v0.1/dataset_stats.json")
if stats_path.exists():
    with open(stats_path, encoding="utf-8") as f:
        stats = json.load(f)

    # Build difficulty_stratification in the format the challenge schema expects
    stats["difficulty_stratification"] = {
        "easy":   ", ".join(pair_ids_by_diff["easy"]),
        "medium": ", ".join(pair_ids_by_diff["medium"]),
        "hard":   ", ".join(pair_ids_by_diff["hard"]),
    }
    stats["difficulty_counts"] = {
        "easy":   difficulty_counts["easy"],
        "medium": difficulty_counts["medium"],
        "hard":   difficulty_counts["hard"],
    }
    stats["difficulty_per_probe"] = {
        probe: dict(d) for probe, d in per_probe_diff.items()
    }

    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"\nUpdated {stats_path}")

print("\nDone. All pairs now have a 'difficulty' field.")
print("Difficulty_stratification added to dataset_stats.json.")
