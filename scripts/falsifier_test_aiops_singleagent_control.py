"""Pre-registered control test, requested to close a specific confound in
Section V-H's AIOps Falsifier result.

The result reported there (single-agent 21.3% -> multi-agent+Falsifier 33.3%,
p=0.023) changes TWO things at once relative to the plain single-agent
baseline: (a) it adds the Falsifier verification step, and (b) the
hypothesis being verified comes from the "Reasoning agent" prompt (part of
the multi-agent pipeline) rather than the single-agent prompt. Because both
change together, the result cannot distinguish "the Falsifier capability
itself helps" from "the Falsifier capability only helps when paired with the
multi-agent Reasoning step" -- i.e. it does not by itself show the multi-agent
architecture is doing any of the work, versus a Falsifier bolted directly
onto a single agent.

This script isolates that one variable. Condition tested: single-agent
hypothesis (SAME hypothesis already computed for results_v9_falsifier.json,
reused verbatim -- not re-sampled, to avoid adding new sampling noise to the
one part of the pipeline that is NOT being changed) + Falsifier, using the
identical Falsifier prompt/model/closed-vocabulary design already locked in
falsifier_test_aiops.py. Nothing about the Falsifier's design is changed here
-- only which hypothesis it is asked to check.

Pre-registered comparison: single-agent alone (21.3%, already measured) vs.
single-agent+Falsifier (this script). McNemar's exact test on discordant
pairs against the SAME single-agent baseline used throughout this
evaluation. Run once, scored once, reported regardless of direction --
including if it shows the multi-agent Reasoning step was not necessary for
the AIOps gain.
"""
import json, sys
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/incidents_with_trace_v3.json'))
prior_results = {r['index']: r for r in json.load(open('/tmp/aiops_work/out/results_v9_falsifier.json'))}
print(f'Single-agent+Falsifier control test on {len(incidents)} AIOps incidents')

CATEGORY_KEYWORDS = {
    'CPU fault': ['cpu'],
    'network delay': ['network delay', 'latency', 'delay', 'slow network', 'network slow'],
    'network loss': ['network loss', 'packet loss', 'loss', 'connection drop', 'dropped'],
    'db connection limit': ['connection limit', 'connection pool', 'too many connection', 'session limit'],
    'db  close': ['db close', 'database down', 'connection closed', 'db unavailable', 'database unreachable'],
}
DOMAIN_KW = {'cpu': ['cpu', 'compute'], 'network': ['network', 'connectivity', 'latency', 'packet'], 'db': ['database', 'db ', 'sql', 'connection']}
DOMAIN_OF = {'CPU fault':'cpu','network delay':'network','network loss':'network','db connection limit':'db','db  close':'db'}

def score(hyp, gt):
    t = (hyp or '').lower()
    if any(k in t for k in CATEGORY_KEYWORDS[gt]): return 'exact'
    if any(k in t for k in DOMAIN_KW[DOMAIN_OF[gt]]): return 'partial'
    return 'incorrect'

def call_json(model, prompt, temp=0.2):
    import time
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}],
                                                   response_format={"type":"json_object"}, temperature=temp)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            if 'rate_limit' in str(e).lower() and attempt < 4:
                time.sleep(4 * (attempt + 1))
            else:
                raise

def raw_dump_block(inc):
    lines = []
    for name, s in inc['window_stats'].items():
        lines.append(f"  - {name}: window(mean={s['mean']:.2f}, max={s['max']:.2f}, min={s['min']:.2f}, n={s['n']})")
    for name, s in inc['baseline_stats'].items():
        lines.append(f"  - {name}_baseline: (mean={s['mean']:.2f}, max={s['max']:.2f}, min={s['min']:.2f}, n={s['n']})")
    tw, tb = inc.get('trace_window'), inc.get('trace_baseline')
    if tw: lines.append(f"  - trace_window_raw: {tw}")
    if tb: lines.append(f"  - trace_baseline_raw: {tb}")
    return '\n'.join(lines)

FAULT_CATEGORIES = ['CPU fault', 'network delay', 'network loss', 'db connection limit', 'db  close']

def falsifier(inc, hyp_root_cause, hyp_conf):
    # Identical prompt/model to falsifier_test_aiops.py's falsifier() -- only
    # the hypothesis source differs (single-agent, not Reasoning agent).
    prompt = f"""You are the Falsifier agent. The Reasoning agent investigated entity {inc['entity']} ({inc['object_type']} type) and proposed this hypothesis:
  root_cause = "{hyp_root_cause}"
  confidence = {hyp_conf}

Below is the COMPLETE raw telemetry for this incident -- every metric collected, including signals the Reasoning agent's summary may not have surfaced:

{raw_dump_block(inc)}

Your task is to check this hypothesis against the evidence, actively looking for contradictions rather than assuming it is right. But most hypotheses that correctly read the dominant signal in the data ARE right, and your job is to catch the ones that are not -- not to override every hypothesis with a different guess. Default to "confirmed" unless you find SPECIFIC, CONCRETE evidence in the raw data that contradicts the hypothesis (e.g. the metric it names is not actually anomalous, or a different metric shows a much larger, more clearly causal deviation). Use "refuted" only when a competing category is CLEARLY and SUBSTANTIALLY better supported by the raw data than the original hypothesis -- not merely plausible or equally consistent with it. Use "contested" when you have doubts but no clearly better alternative.

If you refute the hypothesis AND have a specific competing cause in mind, your alternative must be an AFFIRMATIVE root-cause category naming what IS wrong -- one of exactly these five: {FAULT_CATEGORIES}. Do not return a statement that a metric is normal, low, or ruled out (e.g. "Low CPU Usage" is not a valid alternative -- that says CPU is NOT the problem, it does not name what IS). If refuting but you have no confident affirmative alternative from that list, set alternative_category to null.

Respond JSON: {{"verdict": "confirmed" | "contested" | "refuted", "alternative_category": "<one of the five categories above, or null>", "rationale": "<one sentence>"}}"""
    return call_json("gpt-4o-mini", prompt)

outpath = '/tmp/aiops_work/out/results_v10_falsifier_singleagent_control.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    idx = inc['index']
    prior_new = existing.get(idx)
    if prior_new and 'ERROR' not in str(prior_new.get('final_score_after_falsifier', '')):
        print(f'[{n+1}/{len(incidents)}] {idx} skip (already OK)', flush=True)
        continue
    if prior_new:
        results.remove(prior_new)
    base = prior_results[idx]
    gt = base['ground_truth']
    sa_hyp, sa_conf, sa_score = base['single_agent_hyp'], base['single_agent_confidence'], base['single_agent_score']

    try:
        fals = falsifier(inc, sa_hyp, sa_conf)
        verdict = fals.get('verdict', 'confirmed')
        alt = fals.get('alternative_category')
        if verdict == 'refuted' and alt in FAULT_CATEGORIES:
            final_hyp = alt
        else:
            final_hyp = sa_hyp
    except Exception as e:
        verdict, alt, final_hyp = 'ERROR', None, f'ERROR: {e}'
    final_score = score(final_hyp, gt)

    print(f'[{n+1}/{len(incidents)}] {idx} ({gt}): single={sa_score}({sa_hyp}) '
          f'verdict={verdict} alt={alt} final={final_score}({final_hyp})', flush=True)

    results.append({'index': idx, 'ground_truth': gt,
                     'single_agent_hyp': sa_hyp, 'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
                     'falsifier_verdict': verdict, 'falsifier_alternative': alt,
                     'final_hyp_after_falsifier': final_hyp, 'final_score_after_falsifier': final_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
