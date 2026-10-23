# Configuration B — A + trial attributes

**System:** `ROLE_BLOCK` + `FLAT_VOCAB_BLOCK` + `SCHEMA_AC` (see `00_shared_blocks.md`).

**User** (verbatim f-string template):

```
Case ID: {pseudo_id}

Trial characteristics:
{B_FIELD_KEYS, one "- key: value" line each; "(not populated)" if blank}

Protocol excerpt (background, rationale, objectives):
{protocol_excerpt}
```

`B_FIELD_KEYS` (14 fields) are listed in `00_shared_blocks.md` and are all in
`../data/structured_fields.csv`. `protocol_excerpt` is not redistributed in
this release — see `A3_protocol_narrative.md` and the top-level README.
