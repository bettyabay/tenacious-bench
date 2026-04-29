# Failure Taxonomy — Conversion Engine Week 10

**Author:** Bethelhem Abay
**Date:** 2026-04-29
**Source:** Week 10 probe library (32 probes, 8 categories)

---

## Severity Tiers

| Tier | Label | Description | Recovery |
|------|-------|-------------|----------|
| Tier 1 | Brand-Reputation | Irreversible harm to founder/executive trust | None — prevent only |
| Tier 2 | Commercial | Lost deal or pipeline damage | Difficult — requires re-engagement |
| Tier 3 | Quality | Degraded reply rates, signal noise | Moderate — re-send with correction |
| Tier 4 | Infrastructure / Regulatory | GDPR/CAN-SPAM exposure, system reliability | Legal — zero-tolerance |

---

## Taxonomy by Failure Type

### Type 1 — Judgment Failures
Agent has the correct signal but acts on it incorrectly (produces output when it should suppress).

| Probe | Tier | Trigger Signal | Wrong Action | Correct Action |
|-------|------|---------------|--------------|----------------|
| PROBE-A07 | 1 | `disqualifiers: ["anti_offshore"]` | send | suppress |
| PROBE-E01 | 1 | Shared state across thread_ids | send (leaks context) | send (scoped) |
| PROBE-E02 | 3 | Generic peer fixture reuse | send (generic peers) | send (specific peers) |
| PROBE-E03 | 4 | `opt_out_channels` covers all channels | send (SMS) | suppress all |
| PROBE-G03 | 2 | `recipient_role: c_level` + `headcount > 2000` | send | escalate |

### Type 2 — Generation Failures
Agent produces output but the content is wrong.

| Probe | Tier | Root Cause |
|-------|------|-----------|
| PROBE-B03 | 2 | Funding-tier language not adjusted by deal size |
| PROBE-B04 | 2 | Low-confidence funding amount cited as verified fact |
| PROBE-C02 | 3 | Bench commitment constraint ignored |
| PROBE-C04 | 3 | Regulated-industry caveat omitted |
| PROBE-D05 | 1 | Agent doubles down on prospect-rejected recommendation |

### Type 3 — Trajectory Failures
Correct steps but bad outcome due to logic or missing feature.

| Probe | Tier | Root Cause |
|-------|------|-----------|
| PROBE-H01 | 3 | Meeting time proposed in ET only; no local conversion |
| PROBE-H02 | 3 | Proposed time outside valid timezone overlap window |

### Type 4 — Missing Features (NOT BUILT)

| Probe | Missing Capability |
|-------|-------------------|
| PROBE-F02 | No caching / rate-limiting on enrichment API |
| PROBE-H02 | No timezone-aware scheduling validation |
| PROBE-C04 | No regulated-industry tag lookup |

---

## Tier Distribution Across 32 Probes

| Tier | Count | % |
|------|-------|---|
| Tier 1 | 4 | 12.5% |
| Tier 2 | 6 | 18.8% |
| Tier 3 | 14 | 43.8% |
| Tier 4 | 4 | 12.5% |
| Unclassified | 4 | 12.5% |
