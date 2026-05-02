"""
statistical_test.py — Paired bootstrap significance test for ablation results.

Compares three judge variants on the held_out split:
  A — No judge     (baseline agent, τ²-Bench pass_at_1 = 72.67%)
  B — Zero-shot    (scoring_evaluator.py GPT-4o-mini, rule-based prompt)
  C — ORPO judge   (fine-tuned bethelhem21/tenacious-judge-lora)

Outputs 95% CI and p-value for each A→C and B→C comparison.
Results are appended back to ablation_results.json.

Usage:
    python ablations/statistical_test.py
    python ablations/statistical_test.py --results ablations/ablation_results.json
    python ablations/statistical_test.py --bootstrap-iters 10000
"""

import argparse
import json
import random
from pathlib import Path

RESULTS_PATH     = Path(__file__).resolve().parent / "ablation_results.json"
BOOTSTRAP_ITERS  = 10000
ALPHA            = 0.05
SEED             = 3407


# ── bootstrap helpers ─────────────────────────────────────────────────────────

def bootstrap_accuracy(labels: list[int], n_iters: int, rng: random.Random) -> list[float]:
    """Return bootstrap distribution of accuracy over binary label list."""
    n = len(labels)
    samples = []
    for _ in range(n_iters):
        boot = [rng.choice(labels) for _ in range(n)]
        samples.append(sum(boot) / n)
    return samples


def paired_bootstrap_pvalue(
    labels_a: list[int],
    labels_b: list[int],
    n_iters: int,
    rng: random.Random,
) -> float:
    """
    Paired bootstrap p-value: P(acc_b <= acc_a) under null hypothesis.
    One-tailed: tests whether B is significantly better than A.
    """
    assert len(labels_a) == len(labels_b)
    n       = len(labels_a)
    obs_diff = sum(labels_b) / n - sum(labels_a) / n
    count   = 0
    for _ in range(n_iters):
        idxs   = [rng.randint(0, n - 1) for _ in range(n)]
        boot_a = sum(labels_a[i] for i in idxs) / n
        boot_b = sum(labels_b[i] for i in idxs) / n
        if boot_b - boot_a >= obs_diff:
            count += 1
    return count / n_iters


def ci_95(samples: list[float]) -> tuple[float, float]:
    s = sorted(samples)
    lo = s[int(0.025 * len(s))]
    hi = s[int(0.975 * len(s))]
    return round(lo, 4), round(hi, 4)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results",         default=str(RESULTS_PATH))
    parser.add_argument("--bootstrap-iters", type=int, default=BOOTSTRAP_ITERS)
    args = parser.parse_args()

    with open(args.results, encoding="utf-8") as fh:
        data = json.load(fh)

    variants = data.get("variants", {})
    if not variants:
        print("[ERROR] ablation_results.json has no 'variants' key.")
        print("        Run the held_out inference cell in Colab first.")
        return

    rng = random.Random(SEED)

    print(f"\n{'═' * 60}")
    print("  ABLATION SIGNIFICANCE TEST")
    print(f"  Bootstrap iterations : {args.bootstrap_iters}")
    print(f"  Significance level   : α = {ALPHA}")
    print(f"{'═' * 60}")

    stats = {}
    for name, v in variants.items():
        labels   = v["labels"]          # list of 0/1 per held_out pair
        acc      = sum(labels) / len(labels)
        boot     = bootstrap_accuracy(labels, args.bootstrap_iters, rng)
        lo, hi   = ci_95(boot)
        stats[name] = {
            "accuracy"  : round(acc, 4),
            "ci_95"     : [lo, hi],
            "n"         : len(labels),
        }
        print(f"\n  {name}")
        print(f"    accuracy : {acc:.1%}  ({sum(labels)}/{len(labels)})")
        print(f"    95% CI   : [{lo:.4f}, {hi:.4f}]")

    # Pairwise comparisons: A→C and B→C
    comparisons = {}
    pairs_to_test = [("A_no_judge", "C_orpo_judge"),
                     ("B_zero_shot", "C_orpo_judge")]

    print(f"\n{'─' * 60}")
    print("  PAIRWISE COMPARISONS (one-tailed: C better than baseline)")
    print(f"{'─' * 60}")

    for base_name, test_name in pairs_to_test:
        if base_name not in variants or test_name not in variants:
            continue
        la = variants[base_name]["labels"]
        lb = variants[test_name]["labels"]
        p  = paired_bootstrap_pvalue(la, lb, args.bootstrap_iters, rng)
        diff = stats[test_name]["accuracy"] - stats[base_name]["accuracy"]
        sig  = p < ALPHA
        key  = f"{base_name}_vs_{test_name}"
        comparisons[key] = {
            "delta"      : round(diff, 4),
            "p_value"    : round(p, 4),
            "significant": sig,
        }
        print(f"\n  {base_name}  →  {test_name}")
        print(f"    Δ accuracy : {diff:+.1%}")
        print(f"    p-value    : {p:.4f}  {'✓ significant' if sig else '✗ not significant'} (α={ALPHA})")

    # Save results
    data["statistics"] = {name: stats[name] for name in stats}
    data["comparisons"] = comparisons

    with open(args.results, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    print(f"\n{'═' * 60}")
    print(f"  Results saved → {args.results}")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
