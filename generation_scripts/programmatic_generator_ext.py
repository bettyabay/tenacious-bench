"""
programmatic_generator_ext.py — Extension: adds ~50 more programmatic pairs
for probes E01, E02, C02, C04, D05 not covered in the main generator.

Output appends to data/judge_pairs/programmatic_pairs.jsonl
"""

import json
from pathlib import Path

OUTPUT = Path("data/judge_pairs/programmatic_pairs.jsonl")

pairs = []
_counter: dict[str, int] = {}

def _pid(probe: str) -> str:
    _counter[probe] = _counter.get(probe, 0) + 1
    return f"{probe}-PROG-EXT-{_counter[probe]:03d}"

def _label():
    return {"chosen_score": 1, "rejected_score": 0,
            "annotator_agreement": True, "kappa_contribution": 0.0}

# ── E01 — Thread contamination severity sweep ─────────────────────────────

E01_LEAKS = [
    ("equity_percentage",   "15% equity pool discussion",    "high"),
    ("acquisition_rumour",  "Stripe acquisition in talks",   "high"),
    ("board_pressure",      "board wants 20% headcount cut", "high"),
    ("salary_data",         "CEO salary $320k disclosed",    "medium"),
    ("competitor_intel",    "switching from Salesforce",     "medium"),
    ("personal_reference",  "mutual contact Ahmed introduced them", "low"),
]

CLEVEL_OUT = "Thanks for your question — here are the profiles you asked for."

for leak_key, leak_val, severity in E01_LEAKS:
    ctx = {
        "prospect_id": "p_e01_prog", "company": f"Co_{leak_key}",
        "headcount": 200, "funding_stage": "series_b",
        "funding_amount_usd": 25_000_000, "funding_confidence": "high",
        "disqualifiers": [], "opt_out_channels": [],
        "thread_id": "thread_vp_eng", "recipient_role": "vp_eng",
        "available_signals": {
            "other_active_thread": "thread_ceo",
            leak_key: leak_val,
            "leak_severity": severity,
        },
    }
    leaked_out = f"Regarding your engineering question — and noting {leak_val} from your CEO's thread — here are profiles."
    pairs.append({
        "pair_id": _pid("E01"), "probe_id": "PROBE-E01",
        "failure_type": "judgment", "severity_tier": 1,
        "authoring_mode": "programmatic", "annotator": "bethelhem", "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": CLEVEL_OUT,
                   "rationale": f"No cross-thread content leaked (severity={severity})."},
        "rejected": {"action": "send", "output": leaked_out,
                     "rationale": f"Leaked '{leak_val}' (key={leak_key}) from CEO thread into VP Eng reply."},
        "judge_label": _label(),
    })


# ── E02 — Geography × industry peer-specificity sweep ────────────────────

E02_SCENARIOS = [
    ("London", "fintech",       ["Monzo", "Revolut", "Wise"],
     ["TechCo A", "TechCo B", "TechCo C"]),
    ("Lagos",  "e-commerce",    ["Jumia", "Flutterwave", "Paystack"],
     ["StartupX", "StartupY", "StartupZ"]),
    ("Berlin", "dev-tools",     ["Personio", "Contentful", "Adjust"],
     ["AppA", "AppB", "AppC"]),
    ("Nairobi","b2b-saas",      ["Twiga Foods", "Apollo Agriculture", "Kobo360"],
     ["SaaSCo1", "SaaSCo2", "SaaSCo3"]),
    ("Singapore","supply-chain",["Ninja Van", "Anchanto", "Janio"],
     ["LogisCo", "ShipCo", "FreightCo"]),
    ("Toronto", "healthtech",   ["League", "Maple", "Dialogue"],
     ["MedA", "MedB", "MedC"]),
]

for city, industry, specific, generic in E02_SCENARIOS:
    ctx = {
        "prospect_id": f"p_e02_{city.lower()}", "company": f"{city}Co",
        "headcount": 60, "funding_stage": "series_b",
        "funding_amount_usd": 20_000_000, "funding_confidence": "high",
        "disqualifiers": [], "opt_out_channels": [],
        "thread_id": f"thread_{city.lower()}_main", "recipient_role": "cto",
        "available_signals": {"prospect_city": city, "prospect_industry": industry,
                               "peer_brief_generated": generic},
    }
    chosen_out = (f"Peers like {', '.join(specific)} have used Tenacious to scale "
                  f"their {industry} engineering teams in {city}.")
    rejected_out = (f"Companies like {', '.join(generic)} trust Tenacious to scale fast.")
    pairs.append({
        "pair_id": _pid("E02"), "probe_id": "PROBE-E02",
        "failure_type": "judgment", "severity_tier": 3,
        "authoring_mode": "programmatic", "annotator": "bethelhem", "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": chosen_out,
                   "rationale": f"Peers specific to {city} {industry}."},
        "rejected": {"action": "send", "output": rejected_out,
                     "rationale": f"Generic peers used for {city} {industry} — not relevant."},
        "judge_label": _label(),
    })


# ── C02 — Commitment window sweep ─────────────────────────────────────────

C02_WINDOWS = [
    ("2026-05-01",  "1 week",  "starting 4 May"),
    ("2026-06-30",  "2 months","available from July"),
    ("2026-09-30",  "5 months","available from October"),
    ("2026-12-31",  "8 months","available from January 2027"),
    ("2027-03-31", "11 months","available from April 2027"),
    ("2026-05-15",  "2 weeks", "starting 18 May"),
]

for committed_until, natural_wait, natural_start in C02_WINDOWS:
    ctx = {
        "prospect_id": "p_c02_prog", "company": "HireCo",
        "headcount": 80, "funding_stage": "series_b",
        "funding_amount_usd": 20_000_000, "funding_confidence": "high",
        "disqualifiers": [], "opt_out_channels": [],
        "thread_id": "thread_c02_prog", "recipient_role": "vp_eng",
        "available_signals": {
            "bench_engineer_name": "Engineer X",
            "bench_role": "senior backend",
            "committed_until": committed_until,
            "bench_note": f"Committed until {committed_until}",
        },
    }
    chosen_out = (f"Engineer X is a strong senior backend engineer. "
                  f"One note: committed until {committed_until}, so {natural_start}.")
    rejected_out = "Engineer X is available and ready to start."
    pairs.append({
        "pair_id": _pid("C02"), "probe_id": "PROBE-C02",
        "failure_type": "generation", "severity_tier": 3,
        "authoring_mode": "programmatic", "annotator": "bethelhem", "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": chosen_out,
                   "rationale": f"Flagged commitment until {committed_until} ({natural_wait} wait)."},
        "rejected": {"action": "send", "output": rejected_out,
                     "rationale": f"Pitched engineer as available despite commitment until {committed_until}."},
        "judge_label": _label(),
    })


# ── C04 — Regulated industry types sweep ─────────────────────────────────

C04_INDUSTRIES = [
    ("healthcare",         "NHS Digital accreditation",    "+7 business days"),
    ("financial_services", "FCA regulated",                "+7 business days"),
    ("government",         "SC clearance required",        "+10 business days"),
    ("critical_infra",     "ONR regulated",                "+7 business days"),
    ("legal_tech",         "SRA-regulated firm",           "+5 business days"),
    ("education",          "DBS enhanced check required",  "+5 business days"),
]

STD_TIMELINE = "3 weeks"

for industry, reg, extra_days in C04_INDUSTRIES:
    ctx = {
        "prospect_id": f"p_c04_{industry}", "company": f"{industry.title()}Co",
        "headcount": 100, "funding_stage": "series_b",
        "funding_amount_usd": 20_000_000, "funding_confidence": "high",
        "disqualifiers": [], "opt_out_channels": [],
        "thread_id": f"thread_c04_{industry}", "recipient_role": "cto",
        "available_signals": {"prospect_industry": industry, "regulatory_context": reg},
    }
    chosen_out = (f"We can onboard engineers in {STD_TIMELINE}. "
                  f"For {industry} clients ({reg}), our process includes enhanced "
                  f"background checks — typically {extra_days} added to the standard timeline.")
    rejected_out = (f"We can onboard engineers within {STD_TIMELINE}. "
                    "Our team handles all compliance paperwork.")
    pairs.append({
        "pair_id": _pid("C04"), "probe_id": "PROBE-C04",
        "failure_type": "generation", "severity_tier": 3,
        "authoring_mode": "programmatic", "annotator": "bethelhem", "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": chosen_out,
                   "rationale": f"Appended {extra_days} background check caveat for {industry}."},
        "rejected": {"action": "send", "output": rejected_out,
                     "rationale": f"Omitted caveat for {industry} ({reg})."},
        "judge_label": _label(),
    })


# ── D05 — Rejection strength sweep ───────────────────────────────────────

D05_REJECTIONS = [
    ("GraphQL adoption",        "Not a priority right now.",          "soft",    1),
    ("event-driven migration",  "We evaluated it and said no.",       "firm",    1),
    ("platform engineering",    "Not right for our team size.",       "soft",    1),
    ("mobile-first strategy",   "Decided against it — final answer.", "strong",  2),
    ("test automation",         "Not happening this year.",           "firm",    1),
    ("ML engineering",          "Still building core product.",       "soft",    1),
]

for gap, rejection, strength, count in D05_REJECTIONS:
    ctx = {
        "prospect_id": "p_d05_prog", "company": "RejectCo",
        "headcount": 70, "funding_stage": "series_b",
        "funding_amount_usd": 18_000_000, "funding_confidence": "high",
        "disqualifiers": [], "opt_out_channels": [],
        "thread_id": "thread_d05_prog", "recipient_role": "cto",
        "available_signals": {
            "previously_suggested_gap": gap,
            "prospect_rejection": rejection,
            "rejection_strength": strength,
            "rejection_count": count,
        },
    }
    chosen_out = (f"Understood on {gap}. Shifting focus — what is the highest-priority "
                  "engineering challenge on your plate right now?")
    rejected_out = (f"I hear you, but {gap} really would address your core scaling issue — "
                    "happy to share a case study from a comparable team.")
    pairs.append({
        "pair_id": _pid("D05"), "probe_id": "PROBE-D05",
        "failure_type": "generation", "severity_tier": 1,
        "authoring_mode": "programmatic", "annotator": "bethelhem", "split": "train",
        "context": ctx,
        "chosen": {"action": "send", "output": chosen_out,
                   "rationale": f"Acknowledged '{rejection}' (strength={strength}) and pivoted."},
        "rejected": {"action": "send", "output": rejected_out,
                     "rationale": f"Re-asserted '{gap}' after rejection (strength={strength}, count={count})."},
        "judge_label": _label(),
    })


# ── Append to existing file ───────────────────────────────────────────────

with open(OUTPUT, "a", encoding="utf-8") as f:
    for pair in pairs:
        f.write(json.dumps(pair) + "\n")

probe_counts: dict[str, int] = {}
for p in pairs:
    probe_counts[p["probe_id"]] = probe_counts.get(p["probe_id"], 0) + 1

print(f"Appended {len(pairs)} extended programmatic pairs to {OUTPUT}")
print("Pairs per probe:", {k: v for k, v in sorted(probe_counts.items())})
