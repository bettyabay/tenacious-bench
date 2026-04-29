"""
generate_report.py — Generate the Week 11 progress report.

Reads live dataset stats and produces:
  publication/report.html  (open in browser → File > Print > Save as PDF)
  publication/report.pdf   (if weasyprint or fpdf2 is installed)

Usage:
    python publication/generate_report.py
    python publication/generate_report.py --pdf   # force PDF attempt
"""

import argparse
import json
import textwrap
from datetime import date
from pathlib import Path

# ── Load live data ────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent

def load_json(path):
    p = ROOT / path
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def load_jsonl(path):
    p = ROOT / path
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

stats      = load_json("tenacious_bench_v0.1/dataset_stats.json")
train_pairs = load_jsonl("tenacious_bench_v0.1/train/pairs.jsonl")
dev_pairs   = load_jsonl("tenacious_bench_v0.1/dev/pairs.jsonl")
held_pairs  = load_jsonl("tenacious_bench_v0.1/held_out/pairs.jsonl")
all_pairs   = train_pairs + dev_pairs + held_pairs

cost_rows = []
cost_path = ROOT / "cost_log.csv"
if cost_path.exists():
    import csv
    with open(cost_path, encoding="utf-8") as f:
        cost_rows = list(csv.DictReader(f))

total_cost = sum(float(r.get("cost_usd", 0)) for r in cost_rows)

# ── Pick example pairs ────────────────────────────────────────────────────────

def pick(mode=None, probe=None, pairs=all_pairs):
    for p in pairs:
        if mode and p.get("authoring_mode") != mode:
            continue
        if probe and p.get("probe_id") != probe:
            continue
        return p
    return None

ex_prog   = pick(mode="programmatic",  probe="PROBE-B03")
ex_trace  = pick(mode="trace_derived", probe="PROBE-A07")
ex_hand   = pick(mode="hand_authored", probe="PROBE-E01")  # adversarial (3-thread leak)

# ── Multi-LLM pairs (if synthesis has run) ────────────────────────────────────

mllm_pairs = load_jsonl("data/judge_pairs/multi_llm_pairs.jsonl")
mllm_count = len(mllm_pairs)
mllm_probe_counts = {}
for p in mllm_pairs:
    mllm_probe_counts[p["probe_id"]] = mllm_probe_counts.get(p["probe_id"], 0) + 1

total_now = len(all_pairs) + mllm_count

# ── Probe metadata ────────────────────────────────────────────────────────────

PROBE_META = {
    "PROBE-A07": ("Anti-offshore disqualifier",          "Judgment", "Tier 1"),
    "PROBE-E01": ("Thread contamination",                "Judgment", "Tier 1"),
    "PROBE-E02": ("Generic peer names",                  "Judgment", "Tier 3"),
    "PROBE-E03": ("Opt-out channel violation",           "Judgment", "Tier 4"),
    "PROBE-G03": ("C-level escalation",                  "Judgment", "Tier 2"),
    "PROBE-B03": ("Funding-tier language",               "Generation","Tier 2"),
    "PROBE-B04": ("Low-confidence funding claim",        "Generation","Tier 2"),
    "PROBE-C02": ("Bench commitment window",             "Generation","Tier 3"),
    "PROBE-C04": ("Regulated-industry timeline caveat",  "Generation","Tier 3"),
    "PROBE-D05": ("Doubles down after rejection",        "Generation","Tier 1"),
}

RULE_LABELS = [
    "Rule 1 — Suppress disqualifiers (anti_offshore, local_only, do_not_contact, competitor)",
    "Rule 2 — Respect opt-out channels (email / SMS)",
    "Rule 3 — Escalate C-level @ headcount ≥ 2,000",
    "Rule 4 — Block cross-thread context leakage",
    "Rule 5 — Hedge / suppress low-confidence funding claims",
    "Rule 6 — Penalise generic peer names (revise, don't block)",
    "Rule 7 — Pass: well-formed send with no rule triggers",
]

def probe_rule(probe_id):
    rules = {
        "PROBE-A07": 1, "PROBE-E03": 2, "PROBE-G03": 3,
        "PROBE-E01": 4, "PROBE-B04": 5, "PROBE-E02": 6,
        "PROBE-B03": 7, "PROBE-C02": 7, "PROBE-C04": 7, "PROBE-D05": 7,
    }
    n = rules.get(probe_id, 7)
    return RULE_LABELS[n - 1]

# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def bar(count, total, color="#4f8ef7"):
    pct = count / total * 100 if total else 0
    return (f'<div style="display:flex;align-items:center;gap:8px">'
            f'<div style="width:{pct:.1f}%;max-width:300px;height:14px;'
            f'background:{color};border-radius:3px"></div>'
            f'<span style="font-size:13px">{count} ({pct:.1f}%)</span></div>')

def section(title, content, id_=""):
    return f'''
<section id="{id_}" style="margin:0 0 36px 0">
  <h2 style="font-size:20px;font-weight:700;color:#1a1a2e;border-bottom:2px solid #4f8ef7;
             padding-bottom:6px;margin-bottom:18px">{title}</h2>
  {content}
</section>'''

def table(headers, rows, highlight_col=None):
    ths = "".join(f'<th style="padding:8px 14px;text-align:left;background:#1a1a2e;color:#fff;font-size:13px">{h}</th>' for h in headers)
    body = ""
    for i, row in enumerate(rows):
        bg = "#f8f9ff" if i % 2 == 0 else "#fff"
        tds = "".join(
            f'<td style="padding:7px 14px;font-size:13px;'
            f'{"font-weight:600;color:#4f8ef7" if j == highlight_col else ""}">{esc(c)}</td>'
            for j, c in enumerate(row)
        )
        body += f'<tr style="background:{bg}">{tds}</tr>'
    return f'<table style="width:100%;border-collapse:collapse;border:1px solid #e0e4ef;border-radius:6px;overflow:hidden">{ths}{body}</table>'

def callout(label, text, color="#e8f4fd", border="#4f8ef7"):
    return (f'<div style="background:{color};border-left:4px solid {border};'
            f'padding:12px 16px;border-radius:0 6px 6px 0;margin:10px 0;font-size:13px">'
            f'<strong>{esc(label)}</strong> {esc(text)}</div>')

def code_block(text, label=""):
    lbl = f'<div style="font-size:11px;color:#888;margin-bottom:4px">{esc(label)}</div>' if label else ""
    return (f'{lbl}<pre style="background:#1a1a2e;color:#e8f0fe;padding:14px 16px;'
            f'border-radius:6px;font-size:12px;overflow-x:auto;white-space:pre-wrap">'
            f'{esc(text)}</pre>')

def pair_card(pair, title, badge_color="#4f8ef7"):
    if not pair:
        return f'<div style="color:#888;font-style:italic">No pair found for this mode.</div>'
    ctx = pair.get("context", {})
    chosen  = pair.get("chosen", {})
    rejected = pair.get("rejected", {})
    probe_id = pair.get("probe_id", "")
    rule_text = probe_rule(probe_id)
    meta = PROBE_META.get(probe_id, ("", "", ""))

    return f'''
<div style="border:1px solid #e0e4ef;border-radius:8px;overflow:hidden;margin-bottom:20px">
  <div style="background:{badge_color};color:#fff;padding:10px 16px;font-weight:700;font-size:14px">
    {esc(title)} &nbsp;·&nbsp; {esc(pair.get("pair_id",""))} &nbsp;·&nbsp; {esc(probe_id)}: {esc(meta[0])}
  </div>
  <div style="padding:16px">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px">
      <div style="background:#f8f9ff;padding:8px 12px;border-radius:4px;font-size:12px">
        <strong>Company:</strong> {esc(ctx.get("company",""))}
      </div>
      <div style="background:#f8f9ff;padding:8px 12px;border-radius:4px;font-size:12px">
        <strong>Headcount:</strong> {esc(ctx.get("headcount",""))}
      </div>
      <div style="background:#f8f9ff;padding:8px 12px;border-radius:4px;font-size:12px">
        <strong>Funding:</strong> {esc(ctx.get("funding_stage",""))} · {esc(ctx.get("funding_confidence",""))}
      </div>
    </div>
    <div style="background:#f8f9ff;padding:8px 12px;border-radius:4px;font-size:12px;margin-bottom:12px">
      <strong>Disqualifiers:</strong> {esc(ctx.get("disqualifiers",[])) or "none"} &nbsp;&nbsp;
      <strong>Opt-out channels:</strong> {esc(ctx.get("opt_out_channels",[])) or "none"} &nbsp;&nbsp;
      <strong>Recipient:</strong> {esc(ctx.get("recipient_role",""))}
    </div>
    <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:10px 14px;border-radius:0 4px 4px 0;font-size:12px;margin-bottom:12px">
      <strong>Rule fired:</strong> {esc(rule_text)}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="background:#d4edda;padding:8px 12px;border-radius:4px 4px 0 0;font-weight:700;font-size:12px;color:#155724">
          CHOSEN — action: {esc(chosen.get("action",""))}
        </div>
        <div style="background:#f8fff8;border:1px solid #d4edda;padding:10px 12px;border-radius:0 0 4px 4px;font-size:12px">
          <p style="margin:0 0 6px 0"><em>{esc(chosen.get("output","(suppress — no output)"))}</em></p>
          <p style="margin:0;color:#555"><strong>Rationale:</strong> {esc(chosen.get("rationale",""))}</p>
        </div>
      </div>
      <div>
        <div style="background:#f8d7da;padding:8px 12px;border-radius:4px 4px 0 0;font-weight:700;font-size:12px;color:#721c24">
          REJECTED — action: {esc(rejected.get("action",""))}
        </div>
        <div style="background:#fff8f8;border:1px solid #f8d7da;padding:10px 12px;border-radius:0 0 4px 4px;font-size:12px">
          <p style="margin:0 0 6px 0"><em>{esc(rejected.get("output",""))}</em></p>
          <p style="margin:0;color:#555"><strong>Rationale:</strong> {esc(rejected.get("rationale",""))}</p>
        </div>
      </div>
    </div>
  </div>
</div>'''

# ── Build HTML ────────────────────────────────────────────────────────────────

def build_html():
    today = date.today().isoformat()
    overall_probe = stats.get("overall_probe_distribution", {})
    overall_mode  = stats.get("overall_mode_distribution", {})
    splits_data   = stats.get("splits", {})
    total_v01     = stats.get("total_pairs", 203)

    # ── Section 1: Bench Composition ─────────────────────────────────────────
    probe_rows = []
    for pid, (desc, ftype, tier) in PROBE_META.items():
        count = overall_probe.get(pid, 0)
        t_count = splits_data.get("train", {}).get("probe_distribution", {}).get(pid, 0)
        d_count = splits_data.get("dev",   {}).get("probe_distribution", {}).get(pid, 0)
        h_count = splits_data.get("held_out", {}).get("probe_distribution", {}).get(pid, 0)
        m_count = mllm_probe_counts.get(pid, 0)
        probe_rows.append([pid, desc, ftype, tier, str(count), str(m_count),
                           str(t_count), str(d_count), str(h_count)])

    mode_rows = []
    for mode, count in sorted(overall_mode.items()):
        pct = count / total_v01 * 100 if total_v01 else 0
        mode_rows.append([mode, str(count), f"{pct:.1f}%"])
    if mllm_count:
        mode_rows.append(["multi_llm", str(mllm_count), f"{mllm_count/(total_now)*100:.1f}%"])

    split_rows = [
        ["train",    str(splits_data.get("train",{}).get("count",124)),    "61%", "DPO fine-tuning"],
        ["dev",      str(splits_data.get("dev",  {}).get("count",69)),     "34%", "Judge accuracy eval during dev"],
        ["held_out", str(splits_data.get("held_out",{}).get("count",10)),  "5%",  "Sealed — eval after training only"],
    ]

    composition_html = f'''
<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:20px">
  <div>
    <h3 style="font-size:15px;margin:0 0 10px 0;color:#333">Total pairs</h3>
    <div style="font-size:48px;font-weight:800;color:#4f8ef7">{total_now}</div>
    <div style="font-size:13px;color:#666">v0.1: {total_v01} &nbsp;+&nbsp; multi-LLM: {mllm_count}</div>
  </div>
  <div>
    <h3 style="font-size:15px;margin:0 0 10px 0;color:#333">Authoring mode breakdown</h3>
    {"".join(bar(overall_mode.get(m,0) + (mllm_count if m=="multi_llm" else 0), total_now,
                 c) + f'<div style="font-size:12px;color:#555;margin:-4px 0 6px 0">{m}</div>'
     for m, c in [("trace_derived","#4f8ef7"),("programmatic","#7c4dff"),
                  ("hand_authored","#00897b"),("multi_llm","#f57c00")])}
  </div>
</div>
<h3 style="font-size:15px;margin:16px 0 8px 0;color:#333">Probe distribution (v0.1 base)</h3>
{table(["Probe", "Description", "Type", "Tier", "Total (v0.1)", "Multi-LLM", "Train", "Dev", "Held-out"], probe_rows, highlight_col=4)}
<h3 style="font-size:15px;margin:20px 0 8px 0;color:#333">Split strategy</h3>
{table(["Split", "Count", "%", "Purpose"], split_rows)}
<p style="font-size:12px;color:#666;margin-top:8px">
  Seed: <code>random.seed(3407)</code>. Pre-assigned held_out pairs kept; PROBE-E02 seeded from train (pair E02-004).
  Distribution: 75% train / 25% dev from remaining pool after seeding.
</p>'''

    # ── Section 2: Inter-Rater Agreement ─────────────────────────────────────
    ira_html = f'''
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
  <div>
    {table(["Metric", "Value"], [
        ["Sample size", "20 pairs (2 per probe × 10 probes)"],
        ["Annotator 1", "bethelhem (primary, rule-derived)"],
        ["Annotator 2", "GPT-4o via OpenRouter (scheduled)"],
        ["Raw agreement", "Pending — second-annotator pass not yet run"],
        ["Cohen's κ", "Pending"],
        ["Target", "κ ≥ 0.80"],
    ])}
  </div>
  <div>
    <h3 style="font-size:14px;margin:0 0 8px 0">Expected disagreement zones</h3>
    {callout("G03 boundary:", "headcount=2000 (no escalate) vs 2001 (escalate) — 1-unit boundary", "#fff3cd", "#ffc107")}
    {callout("D05 soft rejection:", "\"Not a priority\" may be ambiguous to a second annotator", "#fff3cd", "#ffc107")}
    {callout("E02 specificity:", "threshold of \"how specific is specific enough\" for peer names", "#fff3cd", "#ffc107")}
    {callout("E01 low-severity leak:", "personal references (len < 20 chars) excluded from fingerprint", "#fff3cd", "#ffc107")}
  </div>
</div>
<h3 style="font-size:14px;margin:0 0 8px 0">Process (scheduled for Day 4)</h3>
{code_block("""# 1. Sample 20 pairs from train (2 per probe)
python -c "
import json, random; random.seed(42)
pairs = [json.loads(l) for l in open('tenacious_bench_v0.1/train/pairs.jsonl')]
probes = {}
for p in pairs: probes.setdefault(p['probe_id'], []).append(p)
sample = []
for probe, ps in sorted(probes.items()):
    random.shuffle(ps); sample.extend(ps[:2])
print(f'Sampled {len(sample)} pairs')
"

# 2. Second-annotate with GPT-4o (via scoring_evaluator or custom prompt)
# 3. Compute Cohen's kappa
from sklearn.metrics import cohen_kappa_score
kappa = cohen_kappa_score(annotator_1_labels, annotator_2_labels)
print(f"Cohen's κ = {kappa:.3f}")""", "Inter-rater agreement run script")}
<p style="font-size:12px;color:#666">
  All primary labels are deterministic (derived from the 7-rule priority order), so annotator-1 variance is zero.
  The kappa result entirely reflects how well GPT-4o matches the rule-based labels on boundary cases.
</p>'''

    # ── Section 3: Example Tasks ──────────────────────────────────────────────
    examples_html = f'''
<p style="font-size:13px;color:#555;margin-bottom:16px">
  Three real pairs from the dataset, showing how the 7-rule rubric is applied.
  Each card shows: context signals → rule triggered → correct (chosen) vs wrong (rejected) action.
</p>
{pair_card(ex_prog,  "Example 1 — Programmatic sweep", "#7c4dff")}
{pair_card(ex_trace, "Example 2 — Trace-derived",      "#4f8ef7")}
{pair_card(ex_hand,  "Example 3 — Hand-authored (adversarial)", "#00897b")}'''

    # ── Section 4: Status ─────────────────────────────────────────────────────
    working = [
        ("Dataset v0.1", f"{total_v01} pairs across 10 probes — train/dev/held_out split, contamination PASS (0 violations)"),
        ("Multi-LLM synthesis", f"{mllm_count} pairs generated so far — all scoring 1.00 on judge filter (deepseek + llama-3.1-70b)"),
        ("Judge inference wrapper", "scoring_evaluator.py — OpenRouter, gpt-4o-mini, threshold=0.5, CLI score + evaluate commands"),
        ("Contamination check", "8-gram n-gram overlap on instance-specific fields only — 0 violations across all splits"),
        ("Cost tracking", f"cost_log.csv — ${total_cost:.4f} spent to date (all generation modes 1–4 are $0.00)"),
        ("DPO config", "training/config.yaml — LoRA r=16, β=0.1, lr=2e-4, T4-compatible (fp16, adamw_8bit)"),
        ("Datasheet", "publication/datasheet.md — Gebru + Pushkarna 7-section format, fully populated"),
        ("Synthesis memos", "rafailov_2023.md (DPO loss, hyperparameters) + gu_2024.md (LLM-as-Judge survey) complete"),
    ]
    not_working = [
        ("Inter-rater agreement", "Second-annotator pass with GPT-4o not yet run — scheduled Day 4"),
        ("Multi-LLM synthesis (partial)", f"{mllm_count}/120 target pairs — script running now, will complete ~{120-mllm_count} more pairs"),
        ("DPO training", "Not yet run — waiting for synthesis to complete; Colab T4 script ready"),
        ("Ablation results", "Blocked on training — held_out sealed until after training"),
        ("HuggingFace publish", "Blocked on training — adapter + dataset card not yet uploaded"),
    ]
    plan_rows = [
        ["Day 4 (today)",    "Finish multi-LLM synthesis (120 pairs target)", "synthesize_pairs.py running", "HIGH"],
        ["Day 4",            "Re-run split_pairs.py to incorporate Mode 3 pairs", "After synthesis", "HIGH"],
        ["Day 4",            "Inter-rater agreement pass (GPT-4o, 20 pairs, compute κ)", "scoring_evaluator.py", "HIGH"],
        ["Day 5",            "DPO training on Colab T4 (3 epochs, ~45 min)", "training/train_judge.py", "CRITICAL"],
        ["Day 5",            "Monitor training loss curve, check for collapse", "training_run.log", "HIGH"],
        ["Day 6",            "Ablation eval: run judge on held_out after training", "evaluator/scoring_evaluator.py", "HIGH"],
        ["Day 6",            "Compare A/B/C variants (SFT baseline, DPO, no-judge)", "ablations/", "MEDIUM"],
        ["Day 7",            "Publish LoRA adapter to HuggingFace", "training/judge_adapter/", "MEDIUM"],
        ["Day 7",            "Final README update with training results + HF link", "README.md", "MEDIUM"],
    ]

    status_html = f'''
<h3 style="font-size:15px;margin:0 0 10px 0;color:#155724">What is working</h3>
<div style="margin-bottom:20px">
{"".join(callout("✅ " + item[0] + ":", item[1], "#d4edda", "#28a745") for item in working)}
</div>
<h3 style="font-size:15px;margin:0 0 10px 0;color:#721c24">What is not yet done</h3>
<div style="margin-bottom:20px">
{"".join(callout("⏳ " + item[0] + ":", item[1], "#fff3cd", "#ffc107") for item in not_working)}
</div>
<h3 style="font-size:15px;margin:16px 0 8px 0;color:#333">Plan for Days 4–7</h3>
{table(["Day", "Task", "Script / File", "Priority"], plan_rows, highlight_col=3)}
<div style="margin-top:16px;background:#e8f4fd;border-left:4px solid #4f8ef7;padding:12px 16px;border-radius:0 6px 6px 0;font-size:13px">
  <strong>Critical path:</strong> synthesis finish → split → train → ablate → publish.
  The only hard blocker is Colab T4 availability on Day 5.
  If T4 is unavailable, fall back to Colab A100 (free tier, limited hours) or run fewer epochs.
</div>'''

    # ── Cost section ─────────────────────────────────────────────────────────
    cost_html = f'''
{table(
    ["Date", "Phase", "Model", "Calls", "Tokens In", "Tokens Out", "Cost USD", "Notes"],
    [[r.get("date",""), r.get("phase",""), r.get("model",""), r.get("calls",""),
      r.get("tokens_in",""), r.get("tokens_out",""), f"${float(r.get('cost_usd',0)):.4f}", r.get("notes","")]
     for r in cost_rows]
)}
<div style="margin-top:12px;font-size:15px;font-weight:700;color:#4f8ef7">
  Total spent: ${total_cost:.4f} of $10.00 budget &nbsp;·&nbsp;
  Remaining: ${10 - total_cost:.4f}
</div>'''

    # ── Assemble ──────────────────────────────────────────────────────────────
    toc = """
<nav style="background:#f8f9ff;border:1px solid #e0e4ef;border-radius:8px;padding:16px 20px;margin-bottom:32px">
  <div style="font-weight:700;font-size:14px;margin-bottom:8px;color:#1a1a2e">Contents</div>
  <ol style="margin:0;padding-left:20px;font-size:13px;color:#4f8ef7">
    <li><a href="#composition" style="color:#4f8ef7">Bench Composition</a></li>
    <li><a href="#ira" style="color:#4f8ef7">Inter-Rater Agreement</a></li>
    <li><a href="#examples" style="color:#4f8ef7">Example Tasks with Rubric Application</a></li>
    <li><a href="#status" style="color:#4f8ef7">What Is Working / What Is Not / Plan Days 4–7</a></li>
    <li><a href="#cost" style="color:#4f8ef7">Cost Log</a></li>
  </ol>
</nav>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tenacious-Bench Week 11 — Progress Report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 32px 24px;
         color: #1a1a2e; background: #fff; }}
  a {{ color: #4f8ef7; }}
  code {{ background: #f0f4ff; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  @media print {{
    nav {{ display: none; }}
    section {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;
            padding:32px 36px;border-radius:12px;margin-bottom:32px">
  <div style="font-size:13px;opacity:0.7;margin-bottom:8px">10 Academy TRP1 · Week 11</div>
  <h1 style="font-size:28px;font-weight:800;margin:0 0 8px 0">
    Tenacious-Bench — Sales Agent Evaluation Bench
  </h1>
  <div style="font-size:15px;opacity:0.85">Progress Report · {today}</div>
  <div style="display:flex;gap:24px;margin-top:20px;flex-wrap:wrap">
    <div style="background:rgba(255,255,255,0.1);padding:12px 20px;border-radius:8px;text-align:center">
      <div style="font-size:32px;font-weight:800">{total_now}</div>
      <div style="font-size:12px;opacity:0.8">Total preference pairs</div>
    </div>
    <div style="background:rgba(255,255,255,0.1);padding:12px 20px;border-radius:8px;text-align:center">
      <div style="font-size:32px;font-weight:800">10</div>
      <div style="font-size:12px;opacity:0.8">Probes covered</div>
    </div>
    <div style="background:rgba(255,255,255,0.1);padding:12px 20px;border-radius:8px;text-align:center">
      <div style="font-size:32px;font-weight:800">72.67%</div>
      <div style="font-size:12px;opacity:0.8">Baseline pass_at_1 (τ²-Bench)</div>
    </div>
    <div style="background:rgba(255,255,255,0.1);padding:12px 20px;border-radius:8px;text-align:center">
      <div style="font-size:32px;font-weight:800">${total_cost:.2f}</div>
      <div style="font-size:12px;opacity:0.8">Spent of $10 budget</div>
    </div>
  </div>
</div>

{toc}
{section("1. Bench Composition", composition_html, "composition")}
{section("2. Inter-Rater Agreement", ira_html, "ira")}
{section("3. Example Tasks with Rubric Application", examples_html, "examples")}
{section("4. What Is Working / What Is Not / Plan for Days 4–7", status_html, "status")}
{section("5. Cost Log", cost_html, "cost")}

<div style="margin-top:48px;padding-top:16px;border-top:1px solid #e0e4ef;
            font-size:12px;color:#999;text-align:center">
  Generated {today} · tenacious-bench v0.1 · Path B — Preference-Tuned DPO Judge ·
  bethelhem@10academy.org
</div>
</body>
</html>"""
    return html


# ── Write HTML ────────────────────────────────────────────────────────────────

def write_html(html: str) -> Path:
    out = ROOT / "publication" / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"[report] HTML written -> {out}")
    return out


# ── Write PDF ─────────────────────────────────────────────────────────────────

def write_pdf(html: str) -> bool:
    out = ROOT / "publication" / "report.pdf"
    # Try weasyprint first
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(out))
        print(f"[report] PDF written  -> {out}  (via weasyprint)")
        return True
    except ImportError:
        pass
    # Try pdfkit (wkhtmltopdf wrapper)
    try:
        import pdfkit
        pdfkit.from_string(html, str(out))
        print(f"[report] PDF written  -> {out}  (via pdfkit)")
        return True
    except (ImportError, Exception):
        pass
    print("[report] PDF skipped — install weasyprint or pdfkit to auto-generate PDF.")
    print("         Open report.html in Chrome/Edge → File > Print > Save as PDF")
    return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", action="store_true", help="Also attempt PDF export")
    args = parser.parse_args()

    html = build_html()
    html_path = write_html(html)

    if args.pdf:
        write_pdf(html)
    else:
        print("[report] To export PDF: open report.html in Chrome > Ctrl+P > Save as PDF")
        print(f"         Or re-run with: python publication/generate_report.py --pdf")

    import webbrowser, os
    abs_path = html_path.resolve().as_uri()
    print(f"\n[report] Opening in browser: {abs_path}")
    webbrowser.open(abs_path)


if __name__ == "__main__":
    main()
