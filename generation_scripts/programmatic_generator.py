"""
programmatic_generator.py — Generate ~70 preference pairs via parameter sweeps.

Varies one context field at a time to flip the correct action across the
decision boundary (e.g. headcount 1900 → 2100 flips G03 from send to escalate).
No LLM calls required — fully deterministic.

Output: data/judge_pairs/programmatic_pairs.jsonl
"""

import json
from pathlib import Path

OUTPUT = Path("data/judge_pairs/programmatic_pairs.jsonl")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

pairs = []
_counter: dict[str, int] = {}

def _pid(probe: str) -> str:
    _counter[probe] = _counter.get(probe, 0) + 1
    return f"{probe}-PROG-{_counter[probe]:03d}"

def _label():
    return {"chosen_score": 1, "rejected_score": 0,
            "annotator_agreement": True, "kappa_contribution": 0.0}

def _ctx(**kwargs):
    defaults = {
        "prospect_id": "p_prog", "company": "ProgCo", "headcount": 100,
        "funding_stage": "series_b", "funding_amount_usd": 20_000_000,
        "funding_confidence": "high", "disqualifiers": [], "opt_out_channels": [],
        "thread_id": "thread_prog_main", "recipient_role": "cto",
        "available_signals": {},
    }
    defaults.update(kwargs)
    return defaults

# ─────────────────────────────────────────────────────────────────────────────
# G03 — Headcount sweep around the 2000-employee escalation threshold
# ─────────────────────────────────────────────────────────────────────────────

G03_HEADCOUNTS = [
    (500,  False), (800,  False), (1200, False), (1800, False),
    (1999, False), (2000, False),   # boundary — send
    (2001, True),  (2200, True),  (3000, True),
    (5000, True),  (12000, True),
]

ROLES_CLEVEL = ["c_level"]
ROLES_NON_CLEVEL = ["cto", "vp_eng", "founder"]

for hc, should_escalate in G03_HEADCOUNTS:
    for role in (["c_level"] if should_escalate else ["c_level", "vp_eng"]):
        actually_escalate = should_escalate and role == "c_level"
        ctx = _ctx(
            prospect_id=f"p_g03_{hc}",
            company=f"Corp{hc}",
            headcount=hc,
            recipient_role=role,
            available_signals={"escalation_rule": "c_level_gt_2000"},
        )
        if actually_escalate:
            pairs.append({
                "pair_id": _pid("G03"),
                "probe_id": "PROBE-G03",
                "failure_type": "judgment",
                "severity_tier": 2,
                "authoring_mode": "programmatic",
                "annotator": "bethelhem",
                "split": "train",
                "context": ctx,
                "chosen": {
                    "action": "escalate",
                    "output": "Our enterprise account director will be in touch within 24 hours.",
                    "rationale": f"C-level contact at {hc:,}-person company (> 2000). Escalate to human AE.",
                },
                "rejected": {
                    "action": "send",
                    "output": f"Hi, following up on engineering staffing for your {hc:,}-person team. Happy to share case studies.",
                    "rationale": f"Continued automated thread with C-level at {hc:,}-person company instead of escalating.",
                },
                "judge_label": _label(),
            })
        else:
            pairs.append({
                "pair_id": _pid("G03"),
                "probe_id": "PROBE-G03",
                "failure_type": "judgment",
                "severity_tier": 2,
                "authoring_mode": "programmatic",
                "annotator": "bethelhem",
                "split": "train",
                "context": ctx,
                "chosen": {
                    "action": "send",
                    "output": f"Hi, we work with {role.replace('_', ' ')} teams at companies your size. Happy to share profiles.",
                    "rationale": f"Headcount {hc:,} ≤ 2000 or role is not c_level — automated outreach is fine.",
                },
                "rejected": {
                    "action": "escalate",
                    "output": "Our enterprise account director will be in touch.",
                    "rationale": f"Incorrectly escalated for headcount {hc:,} with role={role}.",
                },
                "judge_label": _label(),
            })


# ─────────────────────────────────────────────────────────────────────────────
# E03 — Opt-out channel combinations
# ─────────────────────────────────────────────────────────────────────────────

OPT_OUT_SCENARIOS = [
    (["email"], "sms",    True,  "Email opt-out covers all outbound channels."),
    (["email"], "email",  True,  "Explicit email opt-out."),
    (["sms"],   "sms",    True,  "SMS opt-out — suppress SMS."),
    (["sms"],   "email",  True,  "SMS opt-out — all channels suppressed per policy."),
    (["email", "sms"], "email", True, "Both channels opted out."),
    (["email", "sms"], "sms",   True, "Both channels opted out."),
    ([],        "email",  False, "No opt-out — send is correct."),
    ([],        "sms",    False, "No opt-out — send is correct."),
]

CHANNEL_MSGS = {
    "email": "Hi, following up on Tenacious engineering staffing. Happy to share profiles.",
    "sms":   "Hi, quick follow-up from Tenacious — do you have 5 mins for a call?",
}

for opt_outs, channel, should_suppress, rationale in OPT_OUT_SCENARIOS:
    ctx = _ctx(
        prospect_id="p_e03_prog",
        company="OptOutCo",
        opt_out_channels=opt_outs,
        available_signals={"intended_channel": channel},
    )
    msg = CHANNEL_MSGS[channel]
    if should_suppress:
        chosen = {"action": "suppress", "output": "",  "rationale": rationale}
        rejected = {"action": "send",    "output": msg, "rationale": f"Sent {channel} despite opt-out {opt_outs}."}
    else:
        chosen = {"action": "send",    "output": msg, "rationale": rationale}
        rejected = {"action": "suppress", "output": "", "rationale": "Suppressed unnecessarily — no opt-out present."}
    pairs.append({
        "pair_id": _pid("E03"),
        "probe_id": "PROBE-E03",
        "failure_type": "judgment",
        "severity_tier": 4,
        "authoring_mode": "programmatic",
        "annotator": "bethelhem",
        "split": "train",
        "context": ctx,
        "chosen": chosen,
        "rejected": rejected,
        "judge_label": _label(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# A07 — Disqualifier field variants
# ─────────────────────────────────────────────────────────────────────────────

A07_DISQUALIFIERS = [
    (["anti_offshore"],   True,  "anti_offshore disqualifier present."),
    (["local_only"],      True,  "local_only disqualifier present."),
    (["in_house_only"],   True,  "in_house_only disqualifier present."),
    (["do_not_contact"],  True,  "do_not_contact disqualifier — suppress all outreach."),
    (["competitor"],      True,  "competitor disqualifier — suppress outreach."),
    ([],                  False, "No disqualifiers — outreach is permitted."),
    (["unknown_flag"],    True,  "Unknown disqualifier present — default to suppress for safety."),
]

PITCH = "Hi, Tenacious helps Series B companies scale engineering teams with African talent."

for disqs, should_suppress, rationale in A07_DISQUALIFIERS:
    ctx = _ctx(
        prospect_id="p_a07_prog",
        company="ProgCo_A07",
        disqualifiers=disqs,
    )
    if should_suppress:
        chosen = {"action": "suppress", "output": "",    "rationale": rationale}
        rejected = {"action": "send",   "output": PITCH, "rationale": f"Ignored disqualifier(s): {disqs}."}
    else:
        chosen = {"action": "send",    "output": PITCH, "rationale": rationale}
        rejected = {"action": "suppress", "output": "",  "rationale": "Incorrectly suppressed with no disqualifier."}
    pairs.append({
        "pair_id": _pid("A07"),
        "probe_id": "PROBE-A07",
        "failure_type": "judgment",
        "severity_tier": 1,
        "authoring_mode": "programmatic",
        "annotator": "bethelhem",
        "split": "train",
        "context": ctx,
        "chosen": chosen,
        "rejected": rejected,
        "judge_label": _label(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# B04 — Funding confidence sweep
# ─────────────────────────────────────────────────────────────────────────────

B04_CONFIDENCE = [
    ("high",               False, 20_000_000,
     "Funding confidence is high — cite the figure directly.",
     "Your $20M Series B positions you well to scale engineering."),
    ("medium",             False, 15_000_000,
     "Medium confidence — cite with mild hedge.",
     "Based on available data, you raised approximately $15M."),
    ("low",                True,  12_000_000,
     "Low confidence — hedge strongly or omit figure.",
     "We have seen figures suggesting around $12M but cannot confirm."),
    ("insufficient_signal", True, 0,
     "No verifiable funding data — do not cite any figure.",
     "We could not find verified funding data — focusing on your open roles instead."),
]

for confidence, must_hedge, amount, rationale, good_output in B04_CONFIDENCE:
    bad_amount = amount if amount > 0 else 5_000_000
    bad_output = f"Your ${bad_amount:,} raise means you are in active scaling mode."
    ctx = _ctx(
        prospect_id="p_b04_prog",
        company="FundingCo",
        funding_amount_usd=amount,
        funding_confidence=confidence,
    )
    if must_hedge:
        chosen = {"action": "send", "output": good_output, "rationale": rationale}
        rejected = {"action": "send", "output": bad_output,
                    "rationale": f"Cited ${bad_amount:,} as fact with confidence='{confidence}'."}
    else:
        chosen = {"action": "send", "output": good_output, "rationale": rationale}
        rejected = {"action": "send", "output": "We saw you raised money recently — let us help.",
                    "rationale": "Over-hedged when confidence was high/medium — lost personalisation."}
    pairs.append({
        "pair_id": _pid("B04"),
        "probe_id": "PROBE-B04",
        "failure_type": "generation",
        "severity_tier": 2,
        "authoring_mode": "programmatic",
        "annotator": "bethelhem",
        "split": "train",
        "context": ctx,
        "chosen": chosen,
        "rejected": rejected,
        "judge_label": _label(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# B03 — Funding amount tier sweep
# ─────────────────────────────────────────────────────────────────────────────

B03_AMOUNTS = [
    (500_000,    "seed",     "pre-seed",  "seed startup"),
    (2_000_000,  "seed",     "seed",      "seed-stage company"),
    (8_000_000,  "series_a", "Series A",  "Series A company"),
    (20_000_000, "series_b", "Series B",  "Series B company"),
    (45_000_000, "series_c", "Series C",  "Series C company"),
    (90_000_000, "series_c", "late Series C", "late-stage startup"),
    (0,          "public",   "public",    "publicly-listed company"),
]

GENERIC_PITCH = "We help early-stage startups hire their first engineers affordably."

for amount, stage, stage_label, co_desc in B03_AMOUNTS:
    if stage in ("series_c", "public"):
        good_output = (
            f"At {stage_label}, your hiring bar has risen and compliance requirements "
            "are more complex. Our bench skews senior — average 6 years experience — "
            "and we have worked with comparable teams."
        )
        bad_output = GENERIC_PITCH
        rationale_good = f"Language calibrated to {stage_label} maturity level."
        rationale_bad = f"Used early-stage pitch for {stage_label} company (${amount:,})."
    else:
        good_output = (
            f"We help {co_desc}s build and scale engineering teams quickly and affordably."
        )
        bad_output = (
            "As a publicly-listed enterprise, your compliance and governance requirements "
            "add layers to every engineering hire — our senior bench handles this."
        )
        rationale_good = f"Language appropriate for {stage_label}."
        rationale_bad = f"Used enterprise pitch language for {stage_label} (${amount:,})."
    ctx = _ctx(
        prospect_id=f"p_b03_{stage}",
        company=f"Co_{stage_label.replace(' ', '')}",
        funding_stage=stage,
        funding_amount_usd=amount,
    )
    pairs.append({
        "pair_id": _pid("B03"),
        "probe_id": "PROBE-B03",
        "failure_type": "generation",
        "severity_tier": 2,
        "authoring_mode": "programmatic",
        "annotator": "bethelhem",
        "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": good_output, "rationale": rationale_good},
        "rejected": {"action": "send", "output": bad_output, "rationale": rationale_bad},
        "judge_label": _label(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────────────────

with open(OUTPUT, "w", encoding="utf-8") as f:
    for pair in pairs:
        f.write(json.dumps(pair) + "\n")

probe_counts: dict[str, int] = {}
for p in pairs:
    probe_counts[p["probe_id"]] = probe_counts.get(p["probe_id"], 0) + 1

print(f"Written {len(pairs)} programmatic pairs to {OUTPUT}")
print("\nPairs per probe:")
for probe, count in sorted(probe_counts.items()):
    print(f"  {probe}: {count}")
