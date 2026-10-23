# Configuration D — B + decision workflow

**System:** `ROLE_BLOCK` + `CLASS_TAXONOMY_BLOCK` + `D_TREE_INSTRUCTION` (with the
decision tree substituted in) + `SCHEMA_DE` (see `00_shared_blocks.md`).

**User** (verbatim f-string template — identical to configuration B's user block):

```
Case ID: {pseudo_id}

Trial characteristics:
{B_FIELD_KEYS, one "- key: value" line each}

Protocol excerpt (background, rationale, objectives):
{protocol_excerpt}
```

Same field source as `B_structured_fields.md`. The reasoning scaffold is
carried entirely in the system prompt (the decision tree + node-answer
schema); the user-visible trial information is unchanged from B.

Model responses are parsed as structured `node_answers` and mechanically
walked to a leaf by `../code/tree_walker.py` — see that file (and Appendix E
of the paper) for the full executable decision-rule logic.
