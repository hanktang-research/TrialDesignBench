# TrialDesignBench

Code and data for **TrialDesignBench: Benchmarking Language Models for Phase-I
Trial Design Against Clinical Knowledge**, an expert-validated benchmark for evaluating large
language models on Phase-I / Phase-I–II oncology dose-finding trial
*design-method selection*.

Yihan Hank Tang\*, Peng Yang\*, Jiayi Xin\*, Tianqi Shang, Xuyang Chen,
Ying Yuan, Yi Lian†, Qi Long†
(\* co-first authors, † co-senior authors)
University of Pennsylvania · The University of Texas MD Anderson Cancer Center

Presented at the NeurIPS 2026 Workshop on World Models for High-Stakes Health
(WMHS). This is a non-archival workshop contribution.

For all 617 trials in the benchmark, this release provides the
reference-standard design labels, the extracted structured fields used to build
the model inputs, the exact prompt templates for every input configuration, and
the code used to construct the reference standard and run the evaluation.

## Contents

```
data/
  reference_standard.csv   617 trials, each with its reference-standard design
                           label, the admissible design set, ranked tiers, and
                           the decision-tree path that produced the label
  structured_fields.csv    617 trials, each with the extracted structured
                           fields used to build the model inputs (paper
                           Appendix: Input Configurations)

code/
  tree_walker.py           the decision workflow as an executable,
                           deterministic walker (paper Appendix: Decision
                           Rules), including the single-agent-vs-combination
                           monotonicity check used to score tree-walk
                           (configuration D/E) responses. Self-contained.
  normalize.py             method-name / class normalization utilities.
                           Self-contained.
  model_config.py          model roster and per-model token budgets.
  runner.py                concurrent, checkpointed model-calling harness.
                           Requires your own model-serving credentials to run
                           (see "Using this release").
  build_prompt.py          assembles the system/user prompt for every
                           (trial, configuration) pair from the shipped data.
  run_full_matrix.py       drives runner + build_prompt + tree_walker over all
                           (model, configuration, trial) combinations.
  full_report_v10.py       aggregates model outputs into the accuracy,
                           balanced-accuracy, macro-F1, kappa, and node-
                           deviation numbers reported in the paper.
  reroute_v9.py            rule-derived reference-standard construction
                           (decision-tree walk over the structured fields).
  late_onset_rule_v9.py    deterministic late-onset (BOIN vs. TITE-BOIN)
                           sub-rule (paper Appendix: Late-onset determination).
  manual_lateonset_overrides.json   expert-review overrides folded into the
                           late-onset rule.
  apply_combination_node_correction.py + combination_node_correction.csv
                           combination-node correction from expert review
                           (single-agent vs. combination re-verification).
  build_reference_standard.py   final BOIN -> 3+3 relabeling (fewer than three
                           prespecified dose levels), producing
                           reference_standard.csv.

prompts/
  00_shared_blocks.md      shared system-prompt blocks (role, class taxonomy,
                           decision tree, response schema) used across
                           configurations
  A_protocol_narrative.md      input configuration A
  B_structured_fields.md       input configuration B
  C_resolved_latents.md        input configuration C
  D_workflow.md                input configuration D
  E_workflow_plus_latents.md   input configuration E
```

## Using this release

- `data/*.csv` and `prompts/*.md` are usable as-is; no code needs to run to
  read or reuse them.
- `code/tree_walker.py`, `code/normalize.py`, and `code/model_config.py` are
  self-contained and run directly against the shipped data.
- `code/runner.py` and `code/run_full_matrix.py` call a model-serving layer;
  running them end to end requires your own serving credentials, which this
  release does not (and cannot) provide.
- `code/reroute_v9.py`, `code/late_onset_rule_v9.py`,
  `code/apply_combination_node_correction.py`,
  `code/build_reference_standard.py`, and `code/build_prompt.py` are included
  for algorithmic transparency: together they document how
  `data/reference_standard.csv` and the `prompts/` templates were derived. They
  reference intermediate working files from the benchmark's construction that
  are not part of this release, so they are not standalone-executable from this
  package alone. Their outputs — `data/reference_standard.csv` and
  `prompts/*.md` — are provided and are complete and usable on their own.

## What is not included, and why

- **Protocol-excerpt and registry-summary narrative text** (substituted into
  configurations A–E) is not redistributed. It is narrative text drawn from
  each trial's own posted protocol, linked publication, or ClinicalTrials.gov
  summary — not a structured field — and is directly retrievable per trial from
  the public AACT database / ClinicalTrials.gov / PubMed via the trial's NCT ID
  (in `reference_standard.csv`); `prompts/` gives the exact template each
  excerpt is substituted into.
- **Intermediate pipeline artifacts** referenced by the construction scripts
  are internal working files from the benchmark's construction and are outside
  the scope of this release.
- **Raw per-trial model responses** are not included; they can be regenerated
  by running `run_full_matrix.py` against the provided data and your own model
  access.

## Data provenance

The trial population and registry-derived fields are drawn from the public
Aggregate Analysis of ClinicalTrials.gov (AACT) database (Tasneem et al., 2012;
doi:10.1371/journal.pone.0033677). See the paper's corpus-construction section
for the full selection methodology.

## Intended use

TrialDesignBench is an evaluation benchmark, not a clinical decision tool. Its
reference-standard designs formalize one specified expert workflow for
contemporary Phase-I dose-finding methodology. Agreement with the reference is
not evidence that a design is clinically optimal, and nothing here should
inform a real trial without review by a qualified biostatistician.

## Citation

```bibtex
@inproceedings{tang2026trialdesignbench,
  title     = {TrialDesignBench: Benchmarking Language Models for Phase-I Trial Design Against Clinical Knowledge},
  author    = {Tang, Yihan Hank and Yang, Peng and Xin, Jiayi and Shang, Tianqi and Chen, Xuyang and Yuan, Ying and Lian, Yi and Long, Qi},
  booktitle = {NeurIPS 2026 Workshop on World Models for High-Stakes Health (WMHS)},
  year      = {2026},
  note      = {Non-archival}
}
```

## License

Code (`code/`) is released under the MIT License. Data (`data/`) and prompt
templates (`prompts/`) are released under CC BY 4.0. See `LICENSE`. The
reference-standard labels and structured fields are derived from the public
AACT database; see AACT's own terms for the underlying registry data.
