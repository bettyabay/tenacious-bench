# =============================================================================
# Tenacious-Bench — ORPO Judge Training (Google Colab T4)
# Model  : unsloth/Qwen2.5-7B-Instruct-bnb-4bit
# Method : ORPO — no reference model, SFT + preference loss in one pass
#          (Hong et al. 2024 — chosen for small dataset < 500 pairs)
#
# HOW TO USE:
#   1. Colab → Runtime → Change runtime type → T4 GPU → Save
#   2. Copy each CELL block into a separate Colab code cell
#   3. Run top to bottom
# =============================================================================


# ── CELL 1 — Install dependencies ────────────────────────────────────────────
get_ipython().system('pip install --upgrade pip')
get_ipython().system('pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"')
get_ipython().system('pip install --no-deps xformers trl peft accelerate bitsandbytes')


# ── CELL 2 — Mount Google Drive ──────────────────────────────────────────────
from google.colab import drive
drive.mount('/content/drive')

import os, json

DRIVE_DATA = "/content/drive/MyDrive/Tenacious Projects/tenacious-bench/Data"

for fname in ["train.jsonl", "dev.jsonl", "held_out.jsonl"]:
    path = f"{DRIVE_DATA}/{fname}"
    ok   = os.path.exists(path)
    sz   = os.path.getsize(path) if ok else 0
    print(f"  {'✓' if ok else '✗ MISSING'}  {fname}  ({sz:,} bytes)")


# ── CELL 3 — Load Qwen2.5-7B with LoRA ───────────────────────────────────────
from unsloth import FastLanguageModel
import torch

max_seq_length = 2048

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name     = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    max_seq_length = max_seq_length,
    load_in_4bit   = True,
)

model = FastLanguageModel.get_peft_model(
    model,
    r                          = 16,
    target_modules             = ["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"],
    lora_alpha                 = 16,
    lora_dropout               = 0,
    bias                       = "none",
    use_gradient_checkpointing = "unsloth",
)


# ── CELL 4 — Quick pre-training inference test ────────────────────────────────
FastLanguageModel.for_inference(model)

inputs = tokenizer(
    ["<|im_start|>user\nYour pricing is too high compared to retail competitors."
     "<|im_end|>\n<|im_start|>assistant\n"],
    return_tensors="pt",
).to("cuda")

outputs = model.generate(**inputs, max_new_tokens=64)
print(tokenizer.batch_decode(outputs))

FastLanguageModel.for_training(model)   # switch back before training


# ── CELL 5 — Verify model and tokenizer ──────────────────────────────────────
if 'tokenizer' in globals() and tokenizer is not None:
    print(f"Tokenizer : {type(tokenizer)}")
    print(f"Vocab size: {len(tokenizer)}")
    print(f"Pad token : {tokenizer.pad_token}")
else:
    print("ERROR: tokenizer not defined — re-run Cell 3")

if 'model' in globals() and model is not None:
    print(f"\nModel : {type(model)}")
    if hasattr(model, 'peft_config'):
        print(f"LoRA  : applied ✓   adapter={model.active_adapter}")
    else:
        print("WARNING: LoRA not applied — re-run Cell 3")
else:
    print("ERROR: model not defined — re-run Cell 3")


# ── CELL 6 — Load data and format for ORPO ───────────────────────────────────
# ORPO needs three columns: prompt | chosen | rejected
# (SFT only needs text; ORPO uses both completions simultaneously)

from datasets import Dataset

JUDGE_SYSTEM = (
    "You are a strict sales-outreach judge. "
    "Apply these 7 rules in priority order: "
    "(1) SUPPRESS if any disqualifier is present (anti_offshore, local_only, do_not_contact). "
    "(2) SUPPRESS if prospect opted out of this channel. "
    "(3) ESCALATE if recipient is C-level AND headcount > 2000. "
    "(4) BLOCK if output references a different thread_id. "
    "(5) BLOCK if funding amount is cited but funding_confidence is low. "
    "(6) PENALISE if peer company names are generic. "
    "(7) PASS if none of the above apply. "
    'Respond with JSON only: {"decision":"PASS"|"BLOCK"|"ESCALATE"|"SUPPRESS",'
    '"rule":"<triggered rule>","reason":"<one sentence>","score":0.0-1.0}'
)

def pair_to_orpo(pair: dict) -> dict | None:
    """
    Convert one preference pair → ORPO format.

    prompt   : judge task + context  (shared for both completions)
    chosen   : correct verdict  (score 1.0, right action)
    rejected : wrong verdict    (score 0.0, the failure the agent made)
    """
    try:
        ctx      = pair["context"]
        chosen   = pair["chosen"]
        rejected = pair["rejected"]

        ctx_str = json.dumps(ctx, separators=(",", ":"))

        # Shared prompt — assistant turn left open for ORPO to fill
        prompt = (
            f"<|im_start|>system\n{JUDGE_SYSTEM}<|im_end|>\n"
            f"<|im_start|>user\n"
            f"CONTEXT: {ctx_str}\n"
            f"DRAFT OUTPUT: {rejected.get('output', '(empty)')}\n"
            f"<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        # Chosen completion — what the judge SHOULD say (block/suppress)
        c_action   = chosen.get("action", "suppress").upper()
        c_decision = "PASS" if c_action == "SEND" else c_action
        chosen_text = json.dumps({
            "decision" : c_decision,
            "rule"     : f"probe_{pair.get('probe_id', '').lower()}",
            "reason"   : chosen.get("rationale", ""),
            "score"    : 1.0,
        })

        # Rejected completion — what the judge SHOULD NOT say
        r_action   = rejected.get("action", "send").upper()
        r_decision = "PASS" if r_action == "SEND" else r_action
        rejected_text = json.dumps({
            "decision" : r_decision,
            "rule"     : "none",
            "reason"   : rejected.get("rationale", ""),
            "score"    : 0.0,
        })

        return {"prompt": prompt, "chosen": chosen_text, "rejected": rejected_text}

    except Exception as e:
        print(f"  [skip] {pair.get('pair_id', '?')}: {e}")
        return None


def build_dataset(path: str) -> Dataset:
    with open(path, encoding="utf-8") as f:
        raw = [json.loads(l) for l in f if l.strip()]
    rows = [r for p in raw if (r := pair_to_orpo(p)) is not None]
    return Dataset.from_list(rows)


train_dataset = build_dataset(f"{DRIVE_DATA}/train.jsonl")
eval_dataset  = build_dataset(f"{DRIVE_DATA}/dev.jsonl")

print(f"train: {len(train_dataset)}, eval: {len(eval_dataset)}")
print("\nSample prompt (first 300 chars):")
print(train_dataset[0]["prompt"][:300])
print("\nSample chosen:")
print(train_dataset[0]["chosen"])
print("\nSample rejected:")
print(train_dataset[0]["rejected"])


# ── CELL 7 — ORPO Training ────────────────────────────────────────────────────
# Key difference from SFT:
#   - Uses ORPOTrainer (not SFTTrainer)
#   - Needs prompt + chosen + rejected columns
#   - beta = odds-ratio weight (lambda in the paper, default 0.1)
#   - No reference model needed — saves ~3-4 GB VRAM vs DPO

from trl import ORPOTrainer, ORPOConfig

trainer = ORPOTrainer(
    model         = model,
    tokenizer     = tokenizer,
    train_dataset = train_dataset,
    eval_dataset  = eval_dataset,
    args = ORPOConfig(
        beta                         = 0.1,       # odds-ratio weight (ORPO lambda)
        per_device_train_batch_size  = 2,
        gradient_accumulation_steps  = 4,
        max_steps                    = 60,
        learning_rate                = 2e-4,
        fp16                         = not torch.cuda.is_bf16_supported(),
        bf16                         = torch.cuda.is_bf16_supported(),
        logging_steps                = 1,
        eval_strategy                = "steps",
        eval_steps                   = 20,
        max_length                   = max_seq_length,
        max_prompt_length            = max_seq_length // 2,
        output_dir                   = "outputs",
    ),
)
trainer.train()


# ── CELL 8 — Plot loss curve ──────────────────────────────────────────────────
import matplotlib.pyplot as plt

history     = trainer.state.log_history
steps       = [x['step'] for x in history if 'loss' in x]
loss_values = [x['loss'] for x in history if 'loss' in x]

plt.figure(figsize=(10, 5))
plt.plot(steps, loss_values, color='#ff7f0e', linewidth=2, label='ORPO Loss')
plt.title('Tenacious-Bench: ORPO Training Convergence', fontsize=14, fontweight='bold')
plt.xlabel('Training Steps', fontsize=12)
plt.ylabel('Loss', fontsize=12)
plt.grid(True, linestyle='--', alpha=0.6)
plt.legend()

if loss_values:
    plt.annotate(
        f'Final Loss: {loss_values[-1]:.4f}',
        xy        = (steps[-1], loss_values[-1]),
        xytext    = (steps[-1] - 15, loss_values[-1] + 2),
        arrowprops= dict(facecolor='black', shrink=0.05),
    )

plt.show()
if loss_values:
    print(f"Start loss : {loss_values[0]:.4f}")
    print(f"Final loss : {loss_values[-1]:.4f}")


# ── CELL 9 — Save adapter + push to HuggingFace ──────────────────────────────
# Add your HF token: Colab left sidebar → 🔑 Secrets → key: HF_TOKEN

model.save_pretrained_lora("tenacious_sales_adapter")
tokenizer.save_pretrained("tenacious_sales_adapter")
print("✅ Adapter saved locally")

from google.colab import userdata
hf_token = userdata.get("HF_TOKEN")

model.push_to_hub_lora("bettyabay/tenacious-judge-lora", token=hf_token)
tokenizer.push_to_hub("bettyabay/tenacious-judge-lora", token=hf_token)
print("✅ Pushed → https://huggingface.co/bettyabay/tenacious-judge-lora")


# ── CELL 10 — Load adapter and run inference test ────────────────────────────
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name     = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    max_seq_length = 2048,
    load_in_4bit   = True,
)
model.load_adapter("bettyabay/tenacious-judge-lora")
FastLanguageModel.for_inference(model)

# Feed the rejected (bad) output — judge should BLOCK it
held = json.loads(open(f"{DRIVE_DATA}/held_out.jsonl").readline())
ctx_str = json.dumps(held["context"], separators=(",", ":"))

test_prompt = (
    f"<|im_start|>system\n{JUDGE_SYSTEM}<|im_end|>\n"
    f"<|im_start|>user\n"
    f"CONTEXT: {ctx_str}\n"
    f"DRAFT OUTPUT: {held['rejected']['output']}\n"
    f"<|im_end|>\n"
    f"<|im_start|>assistant\n"
)

inputs  = tokenizer([test_prompt], return_tensors="pt").to("cuda")
outputs = model.generate(**inputs, max_new_tokens=128,
                         temperature=0.0, do_sample=False)
response = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

print(f"pair_id  : {held['pair_id']}")
print(f"probe_id : {held['probe_id']}")
print(f"draft    : {held['rejected']['output'][:120]}")
print(f"\njudge    : {response.split('assistant')[-1].strip()}")
print(f"expected : BLOCK or SUPPRESS  (this is the rejected output)")


# ── CELL 11 — Export to GGUF (optional) ──────────────────────────────────────
model.save_pretrained_gguf("model", tokenizer, quantization_method="q4_k_m")
