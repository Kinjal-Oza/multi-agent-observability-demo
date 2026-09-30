# Follow-up re-runs (September 2026, preliminary)

Re-runs of the paper's key experiments on newer model families, with the paper's
prompts, scoring and agent roles unchanged. Only the models change. One run per
configuration, not peer reviewed; being written up as a follow-up paper.
Results are summarised in the main README under "Follow-up results".

## What's here
- `runner/orpatch.py`: routes the original scripts' OpenAI calls to OpenRouter and maps
  `gpt-4o` → a "big" model and `gpt-4o-mini` → a "small" model. Adds retries so API errors
  are not scored as wrong answers. Prompts, temperatures and scoring are untouched.
- `runner/run_one.sh`: runs one original script (from `scripts/`) with a chosen model pair.
- `runner/analyze.py`: recomputes accuracy, McNemar p-values, Falsifier before/after
  counts and confidence means for the paper's results and every folder in `results/`.
- `results/<model pair>/`: raw per-incident outputs, same format as the paper's `results/`.

| Folder | Big model (reasoner / single agent) | Small model (telemetry / Falsifier) |
|---|---|---|
| gpt4o_rerun | openai/gpt-4o | openai/gpt-4o-mini |
| sonnet55_haiku45 | anthropic/claude-sonnet-5.5 | anthropic/claude-haiku-4.5 |
| opus55_haiku45 | anthropic/claude-opus-5.5 | anthropic/claude-haiku-4.5 |
| gpt56sol_luna | openai/gpt-5.6-sol | openai/gpt-5.6-luna |
| gemini38flash_35flashlite | google/gemini-3.8-flash | google/gemini-3.5-flash-lite |
| llama33_70b_31_8b | meta-llama/llama-3.3-70b-instruct | meta-llama/llama-3.1-8b-instruct |
| llama4_maverick | meta-llama/llama-4-maverick | meta-llama/llama-4-maverick |
| handoff_gpt4o_haiku45 | openai/gpt-4o | anthropic/claude-haiku-4.5 |
| handoff_gpt4o_gpt56luna | openai/gpt-4o | openai/gpt-5.6-luna |

The two `handoff_*` folders contain only the fair context-pollution test and the AIOps
baseline (the summarizer-swap experiment).

## Reproduce
```bash
pip install openai scipy
export OPENROUTER_API_KEY=...        # never commit this
followup/runner/run_one.sh sonnet anthropic/claude-sonnet-5.5 anthropic/claude-haiku-4.5 run_eval_v5.py
python3 followup/runner/analyze.py
```
Scripts used per model pair: `run_eval_v5.py`, `rcaeval_eval_v2.py`,
`context_pollution_fair_test.py`, `falsifier_test_aiops.py`, `falsifier_test_rcaeval.py`.
Runs are written to `followup/runs/` (not needed in git).

Total cost for all nine model pairs was about $34 via OpenRouter.
