"""
trace_derived.py — Convert Week 10 τ²-Bench trace logs into preference pairs.

The trace log (data/raw/trace_log.jsonl) contains simulation-level metrics:
  reward, agent_cost, duration, simulation_id, task_id, domain

Failure patterns extracted:
  - Always-failing tasks (reward=0 on ALL 5 trials): 76, 92, 104
  - High-failure tasks (≥60% failure rate): 11, 34, 83, 72, 106
  - Intermittent tasks (1-2 failures/5): 1, 4, 22, 29, 66, 105, 109

LIMITATION: This metrics log alone cannot produce text preference pairs.
To generate actual (chosen, rejected) text pairs you need full trace content —
agent messages, tool calls, and context snapshots — which must be retrieved
from the simulation backend by simulation_id.

This script does two things:
  1. analyse()  — classifies all tasks by failure pattern, identifies the
                  simulation_ids most useful for trace_derived pairs
  2. build_pairs() — given a directory of full trace JSON files (one per
                     simulation_id), converts failing simulations into
                     schema-compliant preference pairs

Usage:
    # Step 1 — identify failure clusters
    python trace_derived.py analyse \
        --trace data/raw/trace_log.jsonl \
        --out data/raw/failure_clusters.json

    # Step 2 — build pairs (requires full trace content)
    python trace_derived.py build \
        --trace data/raw/trace_log.jsonl \
        --full-traces path/to/full_trace_dir/ \
        --probe-map data/raw/task_probe_map.json \
        --out data/judge_pairs/raw_trace_derived.jsonl \
        --split train
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Known failure clusters from Week 10 analysis
# Maps task_id → probe_id based on probe library categorisation
# Populate this map once the probe library is confirmed
TASK_PROBE_MAP: dict[str, str] = {
    # "76":  "PROBE-???",   # Always fails — update after probe library review
    # "92":  "PROBE-???",
    # "104": "PROBE-???",
}

FAILURE_TIERS = {
    "always":      {"tasks": ["76", "92", "104"], "min_fail_rate": 1.0},
    "high":        {"tasks": ["11", "34", "72", "83", "106"], "min_fail_rate": 0.6},
    "intermittent": {"tasks": ["1", "4", "22", "29", "66", "105", "109"], "min_fail_rate": 0.2},
}


# ---------------------------------------------------------------------------
# Step 1: Analyse
# ---------------------------------------------------------------------------

def load_trace(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def analyse(trace_path: str, out_path: str) -> None:
    records = load_trace(trace_path)

    tasks: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        tasks[r["task_id"]].append(r)

    clusters = {"always_fail": [], "high_fail": [], "intermittent": [], "always_pass": []}
    task_summary = {}

    for task_id, sims in sorted(tasks.items(), key=lambda x: int(x[0])):
        rewards = [s["reward"] for s in sims]
        fail_rate = 1.0 - (sum(rewards) / len(rewards))
        failing_sim_ids = [s["simulation_id"] for s in sims if s["reward"] == 0.0]

        entry = {
            "task_id": task_id,
            "trials": len(sims),
            "fail_rate": round(fail_rate, 2),
            "failing_simulation_ids": failing_sim_ids,
            "probe_id": TASK_PROBE_MAP.get(task_id, "UNMAPPED"),
            "avg_cost_failing": round(
                sum(s["agent_cost"] for s in sims if s["reward"] == 0.0) / max(len(failing_sim_ids), 1), 6
            ),
        }
        task_summary[task_id] = entry

        if fail_rate == 1.0:
            clusters["always_fail"].append(task_id)
        elif fail_rate >= 0.6:
            clusters["high_fail"].append(task_id)
        elif fail_rate > 0.0:
            clusters["intermittent"].append(task_id)
        else:
            clusters["always_pass"].append(task_id)

    result = {
        "source": trace_path,
        "total_simulations": len(records),
        "unique_tasks": len(tasks),
        "pass_at_1": round(sum(r["reward"] for r in records) / len(records), 4),
        "clusters": clusters,
        "task_summary": task_summary,
        "note": (
            "This analysis identifies WHICH simulations failed. "
            "To build text preference pairs, retrieve full trace content "
            "from the simulation backend by simulation_id."
        ),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    print(f"\nSaved to {out_path}")
    print(f"\nAlways-failing tasks (best trace_derived candidates): {clusters['always_fail']}")
    print(f"High-failure tasks:  {clusters['high_fail']}")
    print(f"Intermittent tasks:  {clusters['intermittent']}")


# ---------------------------------------------------------------------------
# Step 2: Build pairs (requires full trace content per simulation)
# ---------------------------------------------------------------------------

def build_pairs(
    trace_path: str,
    full_trace_dir: str,
    probe_map_path: str,
    out_path: str,
    split: str,
) -> None:
    records = load_trace(trace_path)
    failing = [r for r in records if r["reward"] == 0.0]

    probe_map: dict[str, str] = {}
    if os.path.exists(probe_map_path):
        with open(probe_map_path, encoding="utf-8") as f:
            probe_map = json.load(f)

    pairs_written = 0
    skipped = 0

    with open(out_path, "w", encoding="utf-8") as out_f:
        for sim in failing:
            sim_id = sim["simulation_id"]
            task_id = sim["task_id"]
            full_trace_file = Path(full_trace_dir) / f"{sim_id}.json"

            if not full_trace_file.exists():
                skipped += 1
                continue

            with open(full_trace_file, encoding="utf-8") as tf:
                full = json.load(tf)

            probe_id = probe_map.get(task_id, "PROBE-UNKNOWN")
            pair = _convert_trace_to_pair(sim, full, probe_id, split, pairs_written)
            if pair:
                out_f.write(json.dumps(pair) + "\n")
                pairs_written += 1

    print(f"Pairs written: {pairs_written}")
    print(f"Skipped (no full trace): {skipped}")


def _convert_trace_to_pair(
    sim: dict,
    full_trace: dict,
    probe_id: str,
    split: str,
    index: int,
) -> dict | None:
    """
    Convert one failing simulation into a (chosen, rejected) preference pair.

    Requires full_trace to have:
      - context: dict — the prospect/job context the agent had
      - agent_output: str — the text the agent produced
      - correct_output: str — the correct output (from task definition)
      - correct_action: str — suppress | escalate | send | regenerate
      - agent_action: str — what the agent actually did

    Adjust field names to match your simulation backend's output format.
    """
    # Extract context from full trace (field names may differ)
    context = full_trace.get("context", full_trace.get("task_context", {}))
    agent_output = full_trace.get("agent_output", full_trace.get("agent_message", ""))
    correct_output = full_trace.get("correct_output", full_trace.get("reference_output", ""))
    agent_action = full_trace.get("agent_action", "send")
    correct_action = full_trace.get("correct_action", "send")

    if not context or not agent_output:
        return None

    probe_short = probe_id.replace("PROBE-", "")
    pair_id = f"{probe_short}-{index:03d}"

    return {
        "pair_id": pair_id,
        "probe_id": probe_id,
        "failure_type": "judgment",
        "severity_tier": 1,
        "authoring_mode": "trace_derived",
        "annotator": "bethelhem",
        "split": split,
        "context": context,
        "chosen": {
            "action": correct_action,
            "output": correct_output,
            "rationale": f"Simulation {sim['simulation_id']} failed (reward=0). Correct action per task definition.",
        },
        "rejected": {
            "action": agent_action,
            "output": agent_output,
            "rationale": f"Agent produced this output but task scored reward=0. Task ID: {sim['task_id']}.",
        },
        "judge_label": {
            "chosen_score": 1,
            "rejected_score": 0,
            "annotator_agreement": False,
            "kappa_contribution": 0.0,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Convert trace logs to preference pairs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyse_p = subparsers.add_parser("analyse", help="Classify tasks by failure rate.")
    analyse_p.add_argument("--trace", required=True)
    analyse_p.add_argument("--out", default="data/raw/failure_clusters.json")

    build_p = subparsers.add_parser("build", help="Build preference pairs from full traces.")
    build_p.add_argument("--trace", required=True)
    build_p.add_argument("--full-traces", required=True, dest="full_traces")
    build_p.add_argument("--probe-map", default="data/raw/task_probe_map.json", dest="probe_map")
    build_p.add_argument("--out", default="data/judge_pairs/raw_trace_derived.jsonl")
    build_p.add_argument("--split", choices=["train", "dev", "held_out"], default="train")

    args = parser.parse_args()

    if args.command == "analyse":
        analyse(args.trace, args.out)
    elif args.command == "build":
        build_pairs(args.trace, args.full_traces, args.probe_map, args.out, args.split)


if __name__ == "__main__":
    main()
