# Week 11 Audit Memo — Conversion Engine Failure Analysis

**Author:** Bethelhem Abay  
**Date:** 2026-04-29  
**Path Selected:** Path B — Preference-Tuned Judge (DPO)  

---

## 1. Baseline Performance

The Conversion Engine was evaluated on τ²-Bench (retail domain, 30 tasks, 5 trials,
150 total simulations) and produced the following results:

| Metric | Value |
|--------|-------|
| `pass_at_1` | **0.7267** |
| 95% CI | [0.6504, 0.7917] |
| Simulations | 150 |
| Infra errors | 0 |
| Avg cost / simulation | $0.0199 |
| Git commit | `d11a97072c49d093f7b5a3e4fe9da95b490d43ba` |

A 72.67% pass rate confirms the generator is functional. The remaining ~27% failure
rate is the target for Week 11. The probe library provides the mechanistic
explanation for where those failures originate.

---

## 2. Probe Library Summary

The agent was evaluated against 32 custom probes across 8 failure categories:

| Status | Count | Share |
|--------|-------|-------|
| PASS | 19 | 59% |
| PARTIAL | 10 | 31% |
| NOT BUILT | 3 | 9% |

The 13-probe gap (41%) is not uniformly distributed. Two clusters account for
the majority of business risk: **judgment failures** and **generation failures**.
This memo focuses on the judgment cluster as the primary driver for Path B selection.

---

## 3. Failure Cluster Analysis

### Cluster 1 — Judgment Failures (5 probes, highest severity)

These probes share one structure: the agent has access to the correct disqualifying
signal in the input context, but produces output anyway. The failure is not that
the agent writes bad text — it is that the agent writes at all when it should not.

**PROBE-A07 — Anti-offshore disqualifier ignored**  
The prospect record contains an explicit anti-offshore flag. The Conversion Engine
reads this field during enrichment but does not route it into the decision gate
before generating outreach. The agent sends a pitch to a prospect who has already
signaled they will not engage. Tier 1 severity: irreversible brand damage if the
prospect is vocal in the founder community.  
*Mechanism:* Missing disqualifier gate between enrichment read and generation step.

**PROBE-E01 — Multi-thread context leakage**  
The agent manages parallel outreach threads to a co-founder and a VP of Engineering
at the same company. The co-founder thread contains deal-sensitive context (equity
discussion framing). The agent leaks a co-founder reference into the VP Eng reply.
Tier 1 severity: the VP receives information that was not meant for them, which
destroys trust with both contacts simultaneously.  
*Mechanism:* Thread context is held in a shared state object. The agent does not
enforce per-recipient context isolation before composing a reply.

**PROBE-E02 — Generic peer fixture reuse**  
The agent's peer-brief step pulls competitor company names to personalise outreach.
The probe reveals the agent reuses the same fixture list across different prospects
in the same session — a London fintech and a Lagos e-commerce company receive
identical "peer" references. Tier 3 severity but high volume: this pattern degrades
reply rates across the full prospect pool, not just edge cases.  
*Mechanism:* Peer-brief generation does not validate that competitor names are
specific to the current prospect's industry, geography, and stage.

**PROBE-E03 — SMS sent after email opt-out**  
A prospect has opted out of email communication. The agent correctly suppresses
the email channel but then routes the message to SMS. The opt-out record covers
all outbound channels, not just email. This is a GDPR and CAN-SPAM exposure.
Tier 4 severity: regulatory risk is binary — one violation can trigger enforcement.  
*Mechanism:* The suppression check is channel-specific. The agent queries
`opted_out_email` but not a unified `opted_out_all_channels` flag.

**PROBE-G03 — C-level escalation not triggered**  
The prospect is a C-level contact at a company with 3,000 employees. Per the
escalation protocol, any C-level engagement above 2,000 headcount requires a
human account executive to take over the thread. The agent continues sending
automated follow-ups. Tier 2 severity: a mishandled C-level thread at a large
enterprise is a lost deal, not just a poor impression.  
*Mechanism:* The escalation rule exists in the system prompt but is not enforced
by a hard gate. The agent interprets it as a soft preference rather than a
mandatory branch condition.

---

### Cluster 2 — Generation Failures (5 probes)

These probes represent cases where the agent produces output but the content is
wrong. They are lower priority for Path B but the judge architecture provides a
partial safety net for them.

**PROBE-B03** — Funding-tier language not adjusted. A $50M Series C prospect
receives the same framing as a $5M Seed prospect. The agent treats all funded
companies identically in its pitch language.

**PROBE-B04** — Low-confidence funding amount cited as fact. The enrichment
source returns a funding figure with `confidence: low`. The agent quotes the
number in the email as verified. This is signal over-claiming.

**PROBE-C02** — Bench commitment note ignored. The agent's own bench data
notes "committed through Q3" for one engineer profile. The agent pitches that
profile's availability without flagging the constraint.

**PROBE-C04** — Regulated-industry caveat omitted. The prospect is in
healthcare. The agent does not append the standard +7-day background check
caveat to timeline estimates.

**PROBE-D05** — Agent doubles down on rejected gap. The prospect explicitly
states they chose not to pursue the suggested technical gap. The agent's next
message reasserts the same recommendation.

---

### Cluster 3 — Trajectory and Missing Features (5 probes)

**PROBE-H01** and **PROBE-H02** are scheduling failures where timezone handling
is absent or wrong. **PROBE-F02** and **PROBE-H02** are NOT BUILT — the
caching/rate-limit guard and timezone validation logic do not exist in the
current implementation. **PROBE-C04** overlaps with a missing feature (no
regulated-industry tag lookup).

---

## 4. Why Judgment Failures Are the Priority Target

The five judgment probes (A07, E01, E02, E03, G03) represent **3 of the 4
severity tiers**, including both Tier 1 probes in the entire taxonomy. They are
also the failure type least addressable by generator improvement: the agent
could write perfect emails and still trigger all five if the judgment gate
is absent. A preference-tuned judge trained on (chosen=stop, rejected=continue)
pairs directly installs the missing gate.

The τ²-Bench ~27% failure rate is consistent with a system where generation is
solid but judgment is inconsistent — exactly the profile these probes document.

---

## 5. Path B Design Implication

Each judgment probe maps directly to a (chosen, rejected) preference pair type:

| Probe | Rejected behavior | Chosen behavior |
|-------|------------------|-----------------|
| PROBE-A07 | Send outreach to disqualified prospect | Abort with disqualification note |
| PROBE-E01 | Reply leaks cross-thread context | Reply scoped to recipient thread only |
| PROBE-E02 | Reuse generic peer fixture | Generate prospect-specific peer names |
| PROBE-E03 | Send SMS to opted-out contact | Suppress all channels, log suppression |
| PROBE-G03 | Continue automated thread | Route to human AE with summary |

These five pair types form the seed of the `judge_pairs.jsonl` dataset to be
built in Days 2–3. Inter-rater agreement target: κ ≥ 0.80 on the judgment
call (send vs. suppress / continue vs. escalate).

---

## 6. Cost Accountability

| Item | Cost |
|------|------|
| τ²-Bench (Week 10, reused) | $0.00 charged to Week 11 |
| Week 11 spend to date | $0.00 |
| Remaining Week 11 budget | **$10.00** |
