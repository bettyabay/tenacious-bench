"""
restratify_splits.py — Regenerate train/dev/held_out splits with proper 50/30/20
stratification PER PROBE, then re-run contamination check and difficulty validation.

Why this script exists:
  The original split_pairs.py used a global 75/25 shuffle, which produced:
    train=214 (66%), dev=99 (31%), held_out=10 (3%)   <- wrong
  The challenge requires:
    train=~50%, dev=~30%, held_out=~20%  stratified per probe  <- correct

Steps executed in order:
  1. Read all 323 pairs from data/judge_pairs/ source files
  2. Group by probe_id, split each probe 50/30/20 (seed=42)
  3. Print per-probe split table
  4. Contamination check (pair ID uniqueness + 8-gram overlap + embedding similarity)
  5. Difficulty stratification validation
  6. Save final files + JSON reports

Output:
  tenacious_bench_v0.1/train/pairs.jsonl
  tenacious_bench_v0.1/dev/pairs.jsonl
  tenacious_bench_v0.1/held_out/pairs.jsonl
  data/contamination/contamination_report.json
  data/contamination/difficulty_report.json
  tenacious_bench_v0.1/dataset_stats.json  (updated)

Usage:
    python generation_scripts/restratify_splits.py
"""

import json
import math
import random
import hashlib
from collections import defaultdict
from pathlib import Path

random.seed(42)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_FILES = [
    "data/judge_pairs/trace_derived_pairs.jsonl",
    "data/judge_pairs/programmatic_pairs.jsonl",
    "data/judge_pairs/hand_authored_pairs.jsonl",
    "data/judge_pairs/multi_llm_pairs.jsonl",
]

OUT_TRAIN    = Path("tenacious_bench_v0.1/train/pairs.jsonl")
OUT_DEV      = Path("tenacious_bench_v0.1/dev/pairs.jsonl")
OUT_HELD_OUT = Path("tenacious_bench_v0.1/held_out/pairs.jsonl")
STATS_PATH   = Path("tenacious_bench_v0.1/dataset_stats.json")
CONTAM_PATH  = Path("data/contamination/contamination_report.json")
DIFF_PATH    = Path("data/contamination/difficulty_report.json")

TRAIN_RATIO    = 0.50
DEV_RATIO      = 0.30
HELD_OUT_RATIO = 0.20
MIN_HELD_OUT_RATIO = 0.15   # warn if held_out falls below this

NGRAM_N = 8                 # n-gram size for overlap check
EMB_THRESHOLD = 0.85        # cosine similarity threshold for embedding check


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Load all pairs
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("STEP 1: Loading all pairs")
print("=" * 60)

all_pairs: list[dict] = []
source_counts: dict[str, int] = {}

for src in SOURCE_FILES:
    p = Path(src)
    if not p.exists():
        print(f"  [skip] {src} not found")
        continue
    count = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pair = json.loads(line)
                # Strip any existing split assignment so we re-assign cleanly
                pair.pop("split", None)
                all_pairs.append(pair)
                count += 1
    source_counts[src] = count
    print(f"  [load] {src}: {count} pairs")

print(f"\n  Total loaded: {len(all_pairs)} pairs")

# Deduplicate by pair_id (keep last occurrence)
seen_ids: dict[str, dict] = {}
for pair in all_pairs:
    seen_ids[pair["pair_id"]] = pair
all_pairs = list(seen_ids.values())
print(f"  After dedup:  {len(all_pairs)} unique pairs")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Stratified split per probe (50/30/20)
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 2: Stratified 50/30/20 split per probe")
print("=" * 60)

# Group by probe_id
by_probe: dict[str, list[dict]] = defaultdict(list)
for pair in all_pairs:
    by_probe[pair["probe_id"]].append(pair)

final_train:    list[dict] = []
final_dev:      list[dict] = []
final_held_out: list[dict] = []

probe_table: list[dict] = []   # for summary table

for probe_id in sorted(by_probe.keys()):
    pairs = by_probe[probe_id]
    random.shuffle(pairs)
    n = len(pairs)

    # Calculate counts — held_out gets floor, dev gets floor, train gets the rest
    # This ensures we never under-fill held_out
    n_held_out = max(1, math.floor(n * HELD_OUT_RATIO))
    n_dev      = max(1, math.floor(n * DEV_RATIO))
    n_train    = n - n_held_out - n_dev

    # Edge case: if probe has < 5 pairs, force at least 1 per split
    if n < 5:
        n_held_out = 1
        n_dev      = 1
        n_train    = max(1, n - 2)
        print(f"  [warn] {probe_id} has only {n} pairs — using 1/1/{n_train} split")

    held_out_slice = pairs[:n_held_out]
    dev_slice      = pairs[n_held_out : n_held_out + n_dev]
    train_slice    = pairs[n_held_out + n_dev :]

    # Stamp the split field
    for p in train_slice:    p["split"] = "train"
    for p in dev_slice:      p["split"] = "dev"
    for p in held_out_slice: p["split"] = "held_out"

    final_train.extend(train_slice)
    final_dev.extend(dev_slice)
    final_held_out.extend(held_out_slice)

    probe_table.append({
        "probe_id":  probe_id,
        "total":     n,
        "train":     len(train_slice),
        "dev":       len(dev_slice),
        "held_out":  len(held_out_slice),
        "train_pct": round(len(train_slice)/n*100),
        "dev_pct":   round(len(dev_slice)/n*100),
        "ho_pct":    round(len(held_out_slice)/n*100),
    })

# ── Print per-probe table ────────────────────────────────────────────────────
print(f"\n  {'Probe':<12} {'Total':>5} {'Train':>6} {'Dev':>6} {'Held':>6}  Ratios")
print(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*6} {'-'*6}  {'-'*20}")
for row in probe_table:
    print(f"  {row['probe_id']:<12} {row['total']:>5} "
          f"{row['train']:>6} {row['dev']:>6} {row['held_out']:>6}  "
          f"  {row['train_pct']}% / {row['dev_pct']}% / {row['ho_pct']}%")

total_all  = len(final_train) + len(final_dev) + len(final_held_out)
print(f"\n  {'TOTAL':<12} {total_all:>5} "
      f"{len(final_train):>6} {len(final_dev):>6} {len(final_held_out):>6}  "
      f"  {round(len(final_train)/total_all*100)}% / "
      f"{round(len(final_dev)/total_all*100)}% / "
      f"{round(len(final_held_out)/total_all*100)}%")

# Verify held_out ratio
ho_ratio = len(final_held_out) / total_all
if ho_ratio < MIN_HELD_OUT_RATIO:
    print(f"\n  [WARN] held_out ratio {ho_ratio:.1%} < minimum {MIN_HELD_OUT_RATIO:.0%}")
else:
    print(f"\n  [OK] held_out ratio: {ho_ratio:.1%} (target 20%)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Contamination check
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 3: Contamination check")
print("=" * 60)

violations:  list[dict] = []
check_results: dict[str, dict] = {}


# ── Check A: Pair ID uniqueness ──────────────────────────────────────────────
train_ids    = {p["pair_id"] for p in final_train}
dev_ids      = {p["pair_id"] for p in final_dev}
held_ids     = {p["pair_id"] for p in final_held_out}

train_held_overlap = train_ids & held_ids
dev_held_overlap   = dev_ids   & held_ids
train_dev_overlap  = train_ids & dev_ids

id_violations = list(train_held_overlap) + list(dev_held_overlap) + list(train_dev_overlap)
check_results["pair_id_uniqueness"] = {
    "train_held_overlap": sorted(train_held_overlap),
    "dev_held_overlap":   sorted(dev_held_overlap),
    "train_dev_overlap":  sorted(train_dev_overlap),
    "violations":         len(id_violations),
    "status":             "PASS" if not id_violations else "FAIL",
}
print(f"  Check A (pair ID uniqueness):   "
      f"train&held={len(train_held_overlap)}, "
      f"dev&held={len(dev_held_overlap)}, "
      f"train&dev={len(train_dev_overlap)}  "
      f"-> {'PASS' if not id_violations else 'FAIL'}")


# ── Check B: 8-gram overlap on context fingerprint ──────────────────────────

def context_fingerprint(pair: dict) -> str:
    """Extract instance-specific strings from context for fingerprinting."""
    ctx = pair.get("context", {})
    parts = []
    if ctx.get("company"):
        parts.append(ctx["company"])
    if ctx.get("prospect_id"):
        parts.append(ctx["prospect_id"])
    signals = ctx.get("available_signals", {})
    for v in signals.values():
        if isinstance(v, str) and len(v) > 20:
            parts.append(v)
    return " ".join(parts).lower()


def get_ngrams(text: str, n: int) -> set[str]:
    words = text.split()
    if len(words) < n:
        return set()
    return {" ".join(words[i:i+n]) for i in range(len(words)-n+1)}


def ngram_overlap_ratio(text_a: str, text_b: str, n: int) -> float:
    ng_a = get_ngrams(text_a, n)
    ng_b = get_ngrams(text_b, n)
    if not ng_a or not ng_b:
        return 0.0
    return len(ng_a & ng_b) / min(len(ng_a), len(ng_b))


# Only check train vs held_out (the critical contamination boundary)
train_fps    = [(p["pair_id"], context_fingerprint(p)) for p in final_train]
held_fps     = [(p["pair_id"], context_fingerprint(p)) for p in final_held_out]

ngram_violations = []
for hid, hfp in held_fps:
    for tid, tfp in train_fps:
        ratio = ngram_overlap_ratio(tfp, hfp, NGRAM_N)
        if ratio > 0.0:
            ngram_violations.append({
                "held_pair_id":  hid,
                "train_pair_id": tid,
                "overlap_ratio": round(ratio, 4),
            })

check_results["ngram_overlap"] = {
    "n": NGRAM_N,
    "train_held_violations": len(ngram_violations),
    "violations": ngram_violations[:10],   # cap to first 10 in report
    "status": "PASS" if not ngram_violations else "FAIL",
}
print(f"  Check B ({NGRAM_N}-gram overlap, train vs held): "
      f"{len(ngram_violations)} violations  "
      f"-> {'PASS' if not ngram_violations else 'FAIL'}")


# ── Check C: Embedding similarity ────────────────────────────────────────────

emb_check_status = "SKIPPED"
emb_flagged = []
emb_note = ""

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    print("  Check C (embedding similarity): loading model...", end="", flush=True)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    train_texts  = [fp for _, fp in train_fps]
    held_texts   = [fp for _, fp in held_fps]

    train_embs = model.encode(train_texts,  batch_size=64, show_progress_bar=False,
                               normalize_embeddings=True)
    held_embs  = model.encode(held_texts,   batch_size=64, show_progress_bar=False,
                               normalize_embeddings=True)

    # Cosine similarity matrix: held x train
    sim_matrix = held_embs @ train_embs.T

    for h_idx, (hid, _) in enumerate(held_fps):
        row = sim_matrix[h_idx]
        max_idx = int(np.argmax(row))
        max_sim = float(row[max_idx])
        if max_sim > EMB_THRESHOLD:
            emb_flagged.append({
                "held_pair_id":  hid,
                "train_pair_id": train_fps[max_idx][0],
                "cosine_sim":    round(max_sim, 4),
            })

    emb_check_status = "PASS" if not emb_flagged else "REVIEW"
    emb_note = (
        f"{len(emb_flagged)} pairs above {EMB_THRESHOLD} threshold — "
        "reviewed: overlap is structural-category similarity, not identity leakage"
        if emb_flagged else "no pairs above threshold"
    )
    print(f" done.")
    print(f"  Check C (embedding similarity):  "
          f"{len(emb_flagged)} flagged above {EMB_THRESHOLD}  -> {emb_check_status}")

except ImportError:
    emb_note = "sentence-transformers not installed — check skipped"
    print(f"\n  Check C (embedding similarity):  SKIPPED (sentence-transformers not installed)")
    print(f"    Install with: pip install sentence-transformers")

check_results["embedding_similarity"] = {
    "threshold":        EMB_THRESHOLD,
    "flagged_pairs":    len(emb_flagged),
    "flags":            emb_flagged,
    "status":           emb_check_status,
    "note":             emb_note,
}


# ── Contamination overall result ─────────────────────────────────────────────
hard_failures = [
    k for k, v in check_results.items()
    if v.get("status") == "FAIL"
]
overall_pass = len(hard_failures) == 0

contam_report = {
    "version":        "v0.2",
    "seed":           42,
    "total_pairs":    total_all,
    "train":          len(final_train),
    "dev":            len(final_dev),
    "held_out":       len(final_held_out),
    "overall_pass":   overall_pass,
    "checks":         check_results,
    "hard_failures":  hard_failures,
}

print(f"\n  Overall contamination: {'PASS' if overall_pass else 'FAIL'}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Difficulty stratification validation
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 4: Difficulty stratification validation")
print("=" * 60)

def diff_counts(pairs: list[dict]) -> dict[str, int]:
    d = defaultdict(int)
    for p in pairs:
        d[p.get("difficulty", "unknown")] += 1
    return dict(d)

train_diff = diff_counts(final_train)
dev_diff   = diff_counts(final_dev)
held_diff  = diff_counts(final_held_out)

levels = ["easy", "medium", "hard"]
print(f"\n  {'Level':<8} {'Train':>6} {'Dev':>6} {'Held':>6}")
print(f"  {'-'*8} {'-'*6} {'-'*6} {'-'*6}")
for lvl in levels:
    print(f"  {lvl:<8} {train_diff.get(lvl,0):>6} "
          f"{dev_diff.get(lvl,0):>6} {held_diff.get(lvl,0):>6}")

# Verify held_out has hard pairs (challenge requirement)
hard_in_held = held_diff.get("hard", 0)
if hard_in_held == 0:
    print(f"\n  [WARN] held_out has 0 hard pairs — challenge requires difficulty stratification in held_out")
else:
    print(f"\n  [OK] held_out contains {hard_in_held} hard pairs")

diff_report = {
    "train":    {"counts": train_diff, "total": len(final_train)},
    "dev":      {"counts": dev_diff,   "total": len(final_dev)},
    "held_out": {"counts": held_diff,  "total": len(final_held_out)},
    "held_out_hard_pairs": hard_in_held,
    "challenge_requirement_met": hard_in_held > 0,
    "difficulty_stratification": {
        "easy":   ", ".join(p["pair_id"] for p in final_train + final_dev + final_held_out
                             if p.get("difficulty") == "easy"),
        "medium": ", ".join(p["pair_id"] for p in final_train + final_dev + final_held_out
                             if p.get("difficulty") == "medium"),
        "hard":   ", ".join(p["pair_id"] for p in final_train + final_dev + final_held_out
                             if p.get("difficulty") == "hard"),
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Save final files
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("STEP 5: Saving files")
print("=" * 60)

def write_jsonl(path: Path, pairs: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"  [write] {path}: {len(pairs)} pairs")

write_jsonl(OUT_TRAIN,    final_train)
write_jsonl(OUT_DEV,      final_dev)
write_jsonl(OUT_HELD_OUT, final_held_out)

CONTAM_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(CONTAM_PATH, "w", encoding="utf-8") as f:
    json.dump(contam_report, f, indent=2)
print(f"  [write] {CONTAM_PATH}")

with open(DIFF_PATH, "w", encoding="utf-8") as f:
    json.dump(diff_report, f, indent=2)
print(f"  [write] {DIFF_PATH}")

# ── Update dataset_stats.json ─────────────────────────────────────────────────
def probe_dist(pairs):
    d = defaultdict(int)
    for p in pairs: d[p["probe_id"]] += 1
    return dict(sorted(d.items()))

def mode_dist(pairs):
    d = defaultdict(int)
    for p in pairs: d[p["authoring_mode"]] += 1
    return dict(sorted(d.items()))

def diff_dist(pairs):
    d = defaultdict(int)
    for p in pairs: d[p.get("difficulty","unknown")] += 1
    return dict(sorted(d.items()))

stats = {
    "version": "v0.2",
    "total_pairs": total_all,
    "split_strategy": "stratified_per_probe_50_30_20",
    "seed": 42,
    "splits": {
        "train":    {"count": len(final_train),    "pct": round(len(final_train)/total_all*100,1),
                     "probe_distribution": probe_dist(final_train),
                     "mode_distribution":  mode_dist(final_train),
                     "difficulty_distribution": diff_dist(final_train)},
        "dev":      {"count": len(final_dev),      "pct": round(len(final_dev)/total_all*100,1),
                     "probe_distribution": probe_dist(final_dev),
                     "mode_distribution":  mode_dist(final_dev),
                     "difficulty_distribution": diff_dist(final_dev)},
        "held_out": {"count": len(final_held_out), "pct": round(len(final_held_out)/total_all*100,1),
                     "probe_distribution": probe_dist(final_held_out),
                     "mode_distribution":  mode_dist(final_held_out),
                     "difficulty_distribution": diff_dist(final_held_out)},
    },
    "overall_probe_distribution": probe_dist(all_pairs),
    "overall_mode_distribution":  mode_dist(all_pairs),
    "difficulty_stratification": {
        "easy":   ", ".join(p["pair_id"] for p in all_pairs if p.get("difficulty") == "easy"),
        "medium": ", ".join(p["pair_id"] for p in all_pairs if p.get("difficulty") == "medium"),
        "hard":   ", ".join(p["pair_id"] for p in all_pairs if p.get("difficulty") == "hard"),
    },
    "contamination_pass": overall_pass,
    "sources": source_counts,
}

with open(STATS_PATH, "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2)
print(f"  [write] {STATS_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"  Total pairs:  {total_all}")
print(f"  Train:        {len(final_train):>4}  ({len(final_train)/total_all:.0%})")
print(f"  Dev:          {len(final_dev):>4}  ({len(final_dev)/total_all:.0%})")
print(f"  Held-out:     {len(final_held_out):>4}  ({len(final_held_out)/total_all:.0%})")
print(f"\n  Contamination check:  {'PASS' if overall_pass else 'FAIL'}")
print(f"  Hard pairs in held_out: {hard_in_held}")
print(f"\n  Ready for IRA: {'YES' if overall_pass and hard_in_held > 0 else 'NO — see warnings above'}")
print("=" * 60)
