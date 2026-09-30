#!/bin/bash
# Re-run one of the paper's evaluation scripts with a different model pair, unchanged
# prompts and scoring. Requires OPENROUTER_API_KEY in the environment.
# usage: runner/run_one.sh <tag> <big-model> <small-model> <script.py>
#   e.g. runner/run_one.sh sonnet anthropic/claude-sonnet-5.5 anthropic/claude-haiku-4.5 run_eval_v5.py
# "big" replaces gpt-4o (Supervisor/Reasoning/single agent); "small" replaces gpt-4o-mini (Telemetry/Falsifier).
set -e
TAG=$1; BIG=$2; SMALL=$3; S=$4
ROOT=$(cd "$(dirname "$0")/../.." && pwd)          # repo root
R=$ROOT/followup/runs/$TAG; mkdir -p $R/out $R/scripts $R/logs
cp $ROOT/data/*.json $R/out/
printf 'OPENAI_API_KEY=%s\n' "$OPENROUTER_API_KEY" > $R/.key && chmod 600 $R/.key
sed -e "s#/tmp/secrets/openai.env#$R/.key#g" -e "s#/tmp/aiops_work/out/#$R/out/#g" -e "s#/tmp/aiops_work#$R/scripts#g" \
    $ROOT/scripts/$S > $R/scripts/$S
cd $R/scripts
MODEL_BIG=$BIG MODEL_SMALL=$SMALL python3 -u -c "import sys; sys.path.insert(0,'$ROOT/followup/runner'); import orpatch, runpy; runpy.run_path('$S', run_name='__main__')" > $R/logs/${S%.py}.log 2>&1
rm -f $R/.key
