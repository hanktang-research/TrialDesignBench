# Configuration A.3 — protocol narrative

**System:** `ROLE_BLOCK` + `FLAT_VOCAB_BLOCK` + `SCHEMA_AC` (see `00_shared_blocks.md`).

**User** (verbatim f-string template):

```
Case ID: {pseudo_id}

Protocol excerpt (background, rationale, objectives):
{protocol_excerpt}
```

`protocol_excerpt` is a per-trial excerpt (background, rationale, and
objectives sections only) taken from the trial's posted protocol and/or
linked publication. Not redistributed in this release (narrative text
sourced from the protocol document, not a structured field) — see the
top-level README for how to regenerate it for any NCT ID in
`../data/reference_standard.csv`.
