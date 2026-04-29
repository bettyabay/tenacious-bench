"""
split_pairs.py — Combine all authoring modes and split into train/dev/held_out.

Sources (in priority order for held_out seeding):
  - data/judge_pairs/trace_derived_pairs.jsonl
  - data/judge_pairs/programmatic_pairs.jsonl
  - data/judge_pairs/hand_authored_pairs.jsonl
  - data/judge_pairs/multi_llm_pairs.jsonl  (if present)

Split strategy:
  - Pairs pre-assigned to splits (hand_authored) keep their assignment
  - Remaining pairs: 60% train, 20% dev, 20% held_out (after held_out seeding)
  - held_out guaranteed ≥ 1 pair from each of the 8 probes

Output: tenacious_bench_v0.1/{train,dev,held_out}/pairs.jsonl
        + summary stats JSON

Usage:
    python generation_scripts/split_pairs.py
"""

import json
import random
from collections import defaultdict
from pathlib import Path

random.seed(3407)

SOURCES = [
    "data/judge_pairs/trace_derived_pairs.jsonl",
    "data/judge_pairs/programmatic_pairs.jsonl",
    "data/judge_pairs/hand_authored_pairs.jsonl",
    "data/judge_pairs/multi_llm_pairs.jsonl",  # optional
]

OUT_BASE = Path("tenacious_bench_v0.1")
TARGET_PROBES = [
    "PROBE-A07", "PROBE-E01", "PROBE-E02", "PROBE-E03",
    "PROBE-G03", "PROBE-B03", "PROBE-B04", "PROBE-D05",
]

# ── Load all pairs ────────────────────────────────────────────────────────────

all_pairs: list[dict] = []
source_counts: dict[str, int] = {}

for src in SOURCES:
    p = Path(src)
    if not p.exists():
        print(f"  [skip] {src} not found")
        continue
    count = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_pairs.append(json.loads(line))
                count += 1
    source_counts[src] = count
    print(f"  [load] {src}: {count} pairs")

print(f"\nTotal loaded: {len(all_pairs)}")

# ── Separate pre-assigned held_out pairs ─────────────────────────────────────

pre_held_out = [p for p in all_pairs if p.get("split") == "held_out"]
pre_dev      = [p for p in all_pairs if p.get("split") == "dev"]
unassigned   = [p for p in all_pairs if p.get("split") not in ("held_out", "dev")]
pre_train    = [p for p in unassigned if p.get("split") == "train"]
truly_unassigned = [p for p in unassigned if p.get("split") not in ("train",)]

print(f"\nPre-assigned: held_out={len(pre_held_out)}, dev={len(pre_dev)}, train={len(pre_train)}")

# ── Guarantee ≥1 held_out pair per target probe ────────────────────────────

held_out_probes_covered = {p["probe_id"] for p in pre_held_out}
missing_probes = [pr for pr in TARGET_PROBES if pr not in held_out_probes_covered]

if missing_probes:
    print(f"\nSeeding held_out with missing probes: {missing_probes}")
    remaining_train = list(pre_train)
    random.shuffle(remaining_train)
    seeded: list[dict] = []
    for probe in missing_probes:
        candidates = [p for p in remaining_train if p["probe_id"] == probe]
        if candidates:
            chosen = candidates[0]
            seeded.append(chosen)
            remaining_train.remove(chosen)
            print(f"  seeded {probe}: {chosen['pair_id']}")
    pre_held_out.extend(seeded)
    pre_train = [p for p in pre_train if p not in seeded]

# ── Distribute remaining unassigned pairs ────────────────────────────────────

shuffle_pool = pre_train + truly_unassigned
random.shuffle(shuffle_pool)

n = len(shuffle_pool)
# After seeding, remaining pool goes: 75% train, 25% dev
# (held_out already has pre-assigned + seeded)
dev_cut = int(n * 0.25)
auto_dev   = shuffle_pool[:dev_cut]
auto_train = shuffle_pool[dev_cut:]

final_train    = auto_train
final_dev      = auto_dev + pre_dev
final_held_out = pre_held_out

# Update split field on each pair
for p in final_train:    p["split"] = "train"
for p in final_dev:      p["split"] = "dev"
for p in final_held_out: p["split"] = "held_out"

print(f"\nFinal split: train={len(final_train)}, dev={len(final_dev)}, held_out={len(final_held_out)}")
print(f"Total: {len(final_train)+len(final_dev)+len(final_held_out)}")

# ── Verify probe coverage in held_out ────────────────────────────────────────

held_probes = {p["probe_id"] for p in final_held_out}
missing = [pr for pr in TARGET_PROBES if pr not in held_probes]
if missing:
    print(f"\nWARNING: held_out missing probes: {missing}")
else:
    print("\nOK: held_out covers all 8 target probes")

# ── Write output ─────────────────────────────────────────────────────────────

splits = {"train": final_train, "dev": final_dev, "held_out": final_held_out}
for split_name, pairs in splits.items():
    split_dir = OUT_BASE / split_name
    split_dir.mkdir(parents=True, exist_ok=True)
    out_file = split_dir / "pairs.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"  wrote {len(pairs)} pairs -> {out_file}")

# ── Summary stats ─────────────────────────────────────────────────────────────

def probe_dist(pairs):
    d: dict[str, int] = defaultdict(int)
    for p in pairs: d[p["probe_id"]] += 1
    return dict(sorted(d.items()))

def mode_dist(pairs):
    d: dict[str, int] = defaultdict(int)
    for p in pairs: d[p["authoring_mode"]] += 1
    return dict(sorted(d.items()))

total = len(final_train) + len(final_dev) + len(final_held_out)
summary = {
    "version": "v0.1",
    "total_pairs": total,
    "splits": {
        "train": {"count": len(final_train),
                  "pct": round(len(final_train)/total*100, 1),
                  "probe_distribution": probe_dist(final_train),
                  "mode_distribution": mode_dist(final_train)},
        "dev":   {"count": len(final_dev),
                  "pct": round(len(final_dev)/total*100, 1),
                  "probe_distribution": probe_dist(final_dev),
                  "mode_distribution": mode_dist(final_dev)},
        "held_out": {"count": len(final_held_out),
                     "pct": round(len(final_held_out)/total*100, 1),
                     "probe_distribution": probe_dist(final_held_out),
                     "mode_distribution": mode_dist(final_held_out)},
    },
    "overall_probe_distribution": probe_dist(final_train+final_dev+final_held_out),
    "overall_mode_distribution": mode_dist(final_train+final_dev+final_held_out),
    "sources": source_counts,
    "held_out_probe_coverage": sorted(held_probes),
    "target_probes_all_covered": missing == [],
}

stats_path = OUT_BASE / "dataset_stats.json"
with open(stats_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print(f"\nDataset stats -> {stats_path}")
print(json.dumps(summary, indent=2))
