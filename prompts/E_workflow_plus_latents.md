# Configuration E — C + decision workflow

**System:** `ROLE_BLOCK` + `CLASS_TAXONOMY_BLOCK` + `D_TREE_INSTRUCTION` (with the
decision tree substituted in) + `SCHEMA_DE` (see `00_shared_blocks.md`).

**User** (verbatim f-string template):

```
Case ID: {pseudo_id}

Trial characteristics:
{B_FIELD_KEYS, one "- key: value" line each}

Protocol excerpt (background, rationale, objectives):
{protocol_excerpt}

Latent trial characteristics (resolved for you):
{E_LATENT_KEYS, one "- key: value" line each}
- final_ai_ratio: {final_ai_ratio}
- m2_gate: {m2_gate}
- interval_basis: {interval_basis}
```

Same field source as `C_resolved_latents.md`; the reasoning scaffold (system
prompt) is identical to configuration D's. E is the only configuration that
combines both the resolved latents and the decision-tree scaffold.
`protocol_excerpt` is not redistributed in this release — see
`A3_protocol_narrative.md` and the top-level README.
