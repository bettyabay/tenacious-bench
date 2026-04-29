"""
filter_with_judge.py — Quality filter using GPT-4o-mini judge.

Scores all raw pairs and keeps only those where the judge correctly blocks
the rejected output (score ≥ 0.8). Used primarily for multi_llm pairs.

Usage:
    python filter_with_judge.py \
        --input data/judge_pairs/raw_multi_llm.jsonl \
        --out data/judge_pairs/filtered_multi_llm.jsonl \
        --threshold 0.8
"""

# TODO: implement
