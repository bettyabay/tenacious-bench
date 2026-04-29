# Memo: Gebru et al., 2021 — Datasheets for Datasets

**Paper:** "Datasheets for Datasets" — Gebru et al., 2021
**Relevance:** Template for judge_datasheet.md (publication/datasheet.md)

---

## Key Claims

- Dataset documentation should follow a standard format covering motivation, composition, collection, preprocessing, uses, distribution, and maintenance
- Transparency in dataset creation reduces harm from misuse
- Authors are responsible for foreseeable downstream effects

## Seven Sections (Applied to judge_pairs)

1. **Motivation** — Why was judge_pairs created? What probe failures does it address?
2. **Composition** — 200-300 (chosen, rejected) pairs, 8 probes, 4 authoring modes
3. **Collection Process** — trace_derived, programmatic, multi_llm, hand_authored
4. **Preprocessing** — n-gram dedup, embedding similarity filter, time-shift
5. **Uses** — DPO fine-tuning of B2B sales outreach judge
6. **Distribution** — HuggingFace dataset repo (public or gated?)
7. **Maintenance** — Who updates? How often? Contact for errors?

## Application to This Project

Drives the structure of `publication/datasheet.md`. Each section maps directly.

## Caveats

Gebru format assumes static datasets — note that held_out slice is sealed until final eval.
