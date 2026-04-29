# Memo: Rafailov et al., 2023 — Direct Preference Optimisation (DPO)

**Paper:** "Direct Preference Optimization: Your Language Model is Secretly a Reward Model" — Rafailov et al., 2023
**Relevance:** Foundational algorithm for Path B training

---

## Key Claims

- DPO optimises for human preferences without a separate reward model (vs RLHF)
- Uses implicit reward: r(x,y) = β log(π_θ(y|x) / π_ref(y|x))
- Equivalent to RLHF in theory; simpler to implement and more stable to train
- Loss: L_DPO = -E[log σ(β log(π_θ(y_w|x)/π_ref(y_w|x)) - β log(π_θ(y_l|x)/π_ref(y_l|x)))]

## Hyperparameter Choices

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| β (KL penalty) | 0.1 | Standard value from paper |
| Loss type | sigmoid | Default DPO formulation |
| Epochs | 3 | Sufficient for small dataset (200-300 pairs) |
| LoRA r | 16 | Balance of capacity and VRAM |

## Application to This Project

DPO is used instead of RLHF because:
1. No separate reward model required (saves VRAM on T4)
2. More stable training — no reward hacking
3. TRL library has native DPOTrainer support with Unsloth acceleration

## Caveats

- DPO can collapse if chosen/rejected outputs are too similar
- β tuning is dataset-dependent; may need adjustment after initial training run
