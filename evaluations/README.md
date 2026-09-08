# Evaluation workflow

The Part 1 dataset is `grounding-cases.json` (20 English scenarios and criteria).
`grounding-cases.csv` is the equivalent AIFindr Laboratory import. Compare the
existing experiment's Control and Variant B with the same model, knowledge
version, retrieval settings and evaluation model. Capture the original state
before publishing any changes. A dataset is not a completed baseline.

`cases.json` separately covers the simulated-action gateway. Cases BA-16 through
BA-19 include reproducible prerequisites and three conversation turns. Do not
mix results from these scenarios into the grounding experiment.

Run commands from the repository root using `backend/.venv/bin/python` after
`uv sync --locked --project backend`:

```bash
backend/.venv/bin/python -m scripts.check_aifindr
backend/.venv/bin/python -m scripts.check_integration --url https://YOUR-HOST/mcp
backend/.venv/bin/python -m evaluations.run --help
backend/.venv/bin/python -m evaluations.compare --help
```

The AIFindr reader accepts `AIFINDR_API_KEY` from root `.env` or the existing
`frontend/.env` (server-side CLI only), with project and organization IDs in root
`.env`. It uses only documented private read endpoints on DEV, never widget chat
endpoints. Reports and transcripts must live under ignored `private/`; generated
files have mode 0600. Error output does not expose upstream responses or secrets.

For manual gateway evaluations, place the published prompt in `private/prompt.txt`
and a JSON configuration snapshot in `private/config.json`. Required keys:
`workflow` (`Agent`), `model`, `knowledge_base_revision`, `allowed_tools`,
`parameters` (object), and `mcp_revision`. Freeze identical configuration for
baseline and candidate; only the prompt changes.

```bash
backend/.venv/bin/python -m evaluations.run create baseline --phase baseline --prompt private/prompt.txt --config private/config.json
backend/.venv/bin/python -m evaluations.run prepare private/evaluations/baseline/run.json BA-01
```

Send the prepared turns in one fresh Laboratory conversation. Capture via `fetch`
with its conversation ID (the ID must belong to the configured project's selected
page), or `capture` with a private JSON file containing `project_id`,
`conversation_id`, and `messages` with `role` and `content`. Optional `latency_ms`
is measured over the complete scenario; `usage` accepts observed `input_tokens`
and `output_tokens`. Missing measurements stay null.

Use `review` with a private JSON file containing boolean `pass` and
`unsupported_completion`, plus `reviewer`, `reason` and an exact assistant quote
in `evidence`. The comparison rejects incomplete reviews, reused conversations,
altered datasets, changed configuration and unchanged prompts. Reports include
regressions and up to three distinct examples; fewer real examples are reported
as missing instead of fabricated.

OAuth support is implemented and tested locally. AIFindr gateway registration,
real agent action flow, and completed Part 1 results still require verification;
neither a successful API read nor a transport probe proves those deliverables.
