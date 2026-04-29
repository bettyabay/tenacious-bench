"""
train_judge.py — DPO fine-tuning script for the Tenacious-Bench judge model.

Trains a LoRA adapter on tenacious_bench_v0.1/train/pairs.jsonl using Direct
Preference Optimisation (DPO). Designed for Google Colab T4 (free tier, ~15GB VRAM).

Base model: unsloth/llama-3-8b-bnb-4bit
Method:     DPO via TRL DPOTrainer + Unsloth LoRA
Target VRAM: ~12–14 GB (fits T4 with 4-bit quantisation)

Usage (Google Colab):
    # 1. Upload the training/ directory to Colab
    # 2. Install dependencies:
    !pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    !pip install trl datasets transformers accelerate peft bitsandbytes

    # 3. Run:
    !python train_judge.py --config config.yaml

    # 4. The adapter is saved to training/judge_adapter/
"""

import argparse
import json
from pathlib import Path
from typing import Optional

# ── Dependency check ──────────────────────────────────────────────────────────

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML not installed. Run: pip install pyyaml")

try:
    from datasets import Dataset
    from transformers import TrainingArguments
    from trl import DPOTrainer, DPOConfig
    from peft import LoraConfig
    HAS_TRAINING_DEPS = True
except ImportError:
    HAS_TRAINING_DEPS = False
    print("[warn] Training dependencies not installed. Run pip install trl datasets transformers peft bitsandbytes")

try:
    from unsloth import FastLanguageModel
    HAS_UNSLOTH = True
except ImportError:
    HAS_UNSLOTH = False
    print("[warn] Unsloth not installed. Install with:")
    print("  pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")

# ── Prompt formatting ─────────────────────────────────────────────────────────

JUDGE_SYSTEM = (
    "You are a strict sales-outreach judge. "
    "Review the agent context and draft output below. "
    "Apply the 7 priority rules in order: "
    "(1) block disqualifiers, (2) respect opt-outs, (3) escalate C-level >= 2k headcount, "
    "(4) block thread leakage, (5) hedge low-confidence funding, "
    "(6) penalise generic peers, (7) pass otherwise. "
    "Respond with a JSON verdict: {\"decision\": \"PASS\"|\"BLOCK\"|\"ESCALATE\", \"rule\": \"<rule>\", \"reason\": \"<reason>\", \"score\": 0.0-1.0}"
)

def format_context(ctx: dict) -> str:
    """Render a context dict as a compact JSON string for the prompt."""
    return json.dumps(ctx, separators=(",", ":"))


def pair_to_prompt(pair: dict) -> tuple[str, str, str]:
    """
    Convert a preference pair to (prompt, chosen_completion, rejected_completion).
    The prompt is the judge's input (context + draft).
    The chosen/rejected completions are the correct/incorrect verdicts.
    """
    ctx = pair.get("context", {})
    chosen = pair.get("chosen", {})
    rejected = pair.get("rejected", {})

    # Build the shared prompt
    ctx_str = format_context(ctx)
    prompt = (
        f"<|im_start|>system\n{JUDGE_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n"
        f"CONTEXT: {ctx_str}\n"
        f"DRAFT OUTPUT: {{draft}}\n"
        f"<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    # Chosen completion: verdict that matches the chosen action
    chosen_action = chosen.get("action", "send").upper()
    chosen_decision = "PASS" if chosen_action == "SEND" else chosen_action
    chosen_completion = json.dumps({
        "decision": chosen_decision,
        "rule": f"probe_{pair.get('probe_id', '').lower()}",
        "reason": chosen.get("rationale", ""),
        "score": 1.0,
    })

    # Rejected completion: verdict that would have allowed the wrong output
    rejected_action = rejected.get("action", "send").upper()
    rejected_decision = "PASS" if rejected_action == "SEND" else rejected_action
    rejected_completion = json.dumps({
        "decision": rejected_decision,
        "rule": "none",
        "reason": rejected.get("rationale", ""),
        "score": 0.0,
    })

    # Use chosen output in the prompt (judge evaluates the draft; we pair verdicts)
    prompt_with_draft = prompt.replace("{draft}", chosen.get("output", ""))

    return prompt_with_draft, chosen_completion, rejected_completion


def load_pairs(path: str) -> list[dict]:
    records = []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Pairs file not found: {path}")
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_hf_dataset(pairs: list[dict]) -> "Dataset":
    """Convert pairs list to HuggingFace Dataset with prompt/chosen/rejected columns."""
    prompts, chosen_list, rejected_list = [], [], []
    for pair in pairs:
        try:
            prompt, chosen, rejected = pair_to_prompt(pair)
            prompts.append(prompt)
            chosen_list.append(chosen)
            rejected_list.append(rejected)
        except Exception as e:
            print(f"  [skip] {pair.get('pair_id', '?')}: {e}")
    return Dataset.from_dict({
        "prompt": prompts,
        "chosen": chosen_list,
        "rejected": rejected_list,
    })

# ── Training ──────────────────────────────────────────────────────────────────

def train(config_path: str, dry_run: bool = False):
    # Load config
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    print(f"[config] Loaded from {config_path}")
    print(json.dumps(cfg, indent=2))

    if dry_run:
        print("\n[dry-run] Config validated. Exiting before model load.")
        return

    if not HAS_TRAINING_DEPS:
        raise ImportError("Install training dependencies: pip install trl datasets transformers peft bitsandbytes")
    if not HAS_UNSLOTH:
        raise ImportError("Install Unsloth: pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")

    # ── Load model + tokenizer via Unsloth ──────────────────────────────────
    model_cfg = cfg["model"]
    lora_cfg  = cfg["lora"]
    train_cfg = cfg["training"]

    print(f"\n[model] Loading {model_cfg['base_model']} with max_seq_length={model_cfg['max_seq_length']}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_cfg["base_model"],
        max_seq_length=model_cfg["max_seq_length"],
        dtype=None,   # auto (float16 on T4)
        load_in_4bit=model_cfg.get("load_in_4bit", True),
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_cfg["r"],
        target_modules=lora_cfg["target_modules"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg.get("lora_dropout", 0.05),
        bias="none",
        use_gradient_checkpointing=True,
        random_state=3407,
    )

    # ── Load dataset ────────────────────────────────────────────────────────
    train_path = cfg["data"]["train"]
    eval_path  = cfg["data"].get("eval")

    print(f"\n[data] Loading train pairs from {train_path}")
    train_pairs = load_pairs(train_path)
    train_ds = build_hf_dataset(train_pairs)
    print(f"  train pairs: {len(train_ds)}")

    eval_ds = None
    if eval_path:
        print(f"[data] Loading eval pairs from {eval_path}")
        eval_pairs = load_pairs(eval_path)
        eval_ds = build_hf_dataset(eval_pairs)
        print(f"  eval pairs: {len(eval_ds)}")

    # ── DPO training arguments ──────────────────────────────────────────────
    output_dir = cfg["output"]["adapter_dir"]
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    dpo_config = DPOConfig(
        beta=train_cfg["dpo_beta"],
        output_dir=output_dir,
        num_train_epochs=train_cfg["epochs"],
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=train_cfg.get("gradient_accumulation_steps", 4),
        learning_rate=float(train_cfg["learning_rate"]),
        warmup_ratio=train_cfg.get("warmup_ratio", 0.1),
        lr_scheduler_type=train_cfg.get("lr_scheduler_type", "cosine"),
        optim=train_cfg.get("optim", "adamw_8bit"),
        fp16=train_cfg.get("fp16", True),
        bf16=False,   # T4 does not support bf16
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_ds else "no",
        load_best_model_at_end=True if eval_ds else False,
        report_to="none",   # disable W&B for Colab
        max_length=model_cfg["max_seq_length"],
        max_prompt_length=model_cfg["max_seq_length"] // 2,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,   # Unsloth handles reference model internally
        args=dpo_config,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        tokenizer=tokenizer,
    )

    print(f"\n[train] Starting DPO training (epochs={train_cfg['epochs']}, beta={train_cfg['dpo_beta']})")
    trainer.train()

    # ── Save adapter ─────────────────────────────────────────────────────────
    print(f"\n[save] Saving LoRA adapter to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[save] Done. Adapter saved to {output_dir}")

    # ── Log training results ─────────────────────────────────────────────────
    log_path = Path(cfg["output"].get("training_log", "training/training_run.log"))
    with open(log_path, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"\n=== Training run: {datetime.datetime.now().isoformat()} ===\n")
        f.write(f"Base model: {model_cfg['base_model']}\n")
        f.write(f"Train pairs: {len(train_ds)}\n")
        if eval_ds:
            f.write(f"Eval pairs: {len(eval_ds)}\n")
        f.write(f"Epochs: {train_cfg['epochs']}\n")
        f.write(f"Beta: {train_cfg['dpo_beta']}\n")
        f.write(f"LR: {train_cfg['learning_rate']}\n")
        f.write(f"Adapter: {output_dir}\n")

    print(f"[log] Training metadata appended to {log_path}")


# ── Inference test ────────────────────────────────────────────────────────────

def test_inference(adapter_dir: str, config_path: str):
    """Quick sanity check: load the adapter and run one judge call."""
    if not HAS_UNSLOTH:
        raise ImportError("Unsloth required for inference test")

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    model_cfg = cfg["model"]
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter_dir,
        max_seq_length=model_cfg["max_seq_length"],
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    test_context = {
        "prospect_id": "p_test_001",
        "company": "TestCo",
        "headcount": 250,
        "funding_stage": "series_b",
        "funding_amount_usd": 20_000_000,
        "funding_confidence": "high",
        "disqualifiers": ["anti_offshore"],
        "opt_out_channels": [],
        "thread_id": "thread_cto_main",
        "recipient_role": "cto",
        "available_signals": {},
    }
    test_output = "Hi Sarah, I wanted to share some strong senior backend engineers from our bench."

    ctx_str = format_context(test_context)
    prompt = (
        f"<|im_start|>system\n{JUDGE_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n"
        f"CONTEXT: {ctx_str}\n"
        f"DRAFT OUTPUT: {test_output}\n"
        f"<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    import torch
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=128, temperature=0.0, do_sample=False)
    result = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    print("\n[inference test] Input context has anti_offshore disqualifier.")
    print(f"[inference test] Draft: {test_output}")
    print(f"[inference test] Judge verdict: {result}")
    print("[inference test] Expected: BLOCK (disqualifier rule 1)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DPO judge training script (Tenacious-Bench)")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # train subcommand
    train_parser = subparsers.add_parser("train", help="Run DPO training (default)")
    train_parser.add_argument("--config", default="training/config.yaml",
                              help="Path to config.yaml")
    train_parser.add_argument("--dry-run", action="store_true",
                              help="Validate config without loading model")

    # test subcommand
    test_parser = subparsers.add_parser("test", help="Run inference sanity check")
    test_parser.add_argument("--adapter", default="training/judge_adapter",
                             help="Path to saved adapter directory")
    test_parser.add_argument("--config", default="training/config.yaml")

    # Support calling without subcommand: python train_judge.py --config ...
    parser.add_argument("--config", default="training/config.yaml",
                        help="Path to config.yaml (used when no subcommand given)")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "test":
        test_inference(args.adapter, args.config)
    else:
        config = getattr(args, "config", "training/config.yaml")
        dry = getattr(args, "dry_run", False)
        train(config, dry_run=dry)


if __name__ == "__main__":
    main()
