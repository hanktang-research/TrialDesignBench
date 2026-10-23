# Configuration C — B + design factors (resolved latents)

**System:** `ROLE_BLOCK` + `FLAT_VOCAB_BLOCK` + `SCHEMA_AC` (see `00_shared_blocks.md`).

**User** (verbatim f-string template):

```
Case ID: {pseudo_id}

Trial characteristics:
{B_FIELD_KEYS, one "- key: value" line each}

Protocol excerpt (background, rationale, objectives):
{protocol_excerpt}

In addition to the trial characteristics above, the following latent trial characteristics have been established through prior clinical and statistical analysis and are provided as resolved inputs for your recommendation. These represent judgments that would ordinarily require interpretation of the full protocol; they are supplied here directly.
{C_LATENT_KEYS, one "- key: value" line each}
- final_ai_ratio: {final_ai_ratio}
- m2_gate: {m2_gate}
- interval_basis: {interval_basis}
```

`C_LATENT_KEYS` (7 fields) are listed in `00_shared_blocks.md` and are all in
`../data/structured_fields.csv`; `final_ai_ratio`/`interval_basis` are in
`../data/reference_standard.csv` (`ai_ratio`/`interval_basis` columns).
`m2_gate` is an internal escalation-timing-gate diagnostic; where absent it
reads "(not populated)". `protocol_excerpt` is not redistributed in this
release — see `A3_protocol_narrative.md` and the top-level README.
