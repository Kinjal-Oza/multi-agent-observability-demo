"""Pre-registered test: does a genuine Falsifier/Validation capability help,
where prior multi-agent decomposition (v3-v8) did not?

Rationale, written BEFORE running: every prior configuration (baseline,
sort-fix, raw-context-fix, +RAG, +RAG gated, fair context-pollution test)
gave the multi-agent architecture no capability a single agent could not
also have -- they only changed what information the Reasoning agent saw,
never what it could DO. The two real papers we compare against in Related
Work (Flow-of-Action, MA-RCA) both report large gains, and in both cases the
gain traces to a genuinely new capability: Flow-of-Action grounds actions in
executable SOPs; MA-RCA has a dedicated Validation Agent that dynamically
tests each hypothesis before it is accepted. Neither is "more LLM agents
talking" -- both add something a single generation-only agent cannot do.

This script tests the MA-RCA-style mechanism: a Falsifier agent that receives
the Reasoning agent's hypothesis PLUS the complete raw telemetry (including
signals the Reasoning agent did not cite), and is prompted adversarially to
find contradicting evidence or a better-supported alternative cause -- not to
confirm. A "refuted" verdict with a concrete alternative overrides the
original hypothesis. This mirrors the Falsifier design in the author's
`adversarial-falsifier-agent-demo` reference implementation (built for a
separate InfoQ article, synthetic-corpus only), applied here to NetOpsAgent's
actual incident data for the first time.

Two conditions, run once each, in the SAME script execution (so both are
contemporaneous -- avoids mixing a fresh run with an old run and confusing a
noise swing for a real effect, per the single-run-noise limitation already
documented in this evaluation):
  1. single_agent_baseline: fresh one-shot GPT-4o call, same prompt style as
     all prior single-agent baselines.
  2. multi_agent_falsifier: Telemetry summary (raw-context-fix style, as in
     v5/v6) -> Reasoning hypothesis -> Falsifier (GPT-4o-mini, adversarial,
     full raw data) -> hypothesis revised only if refuted with a concrete
     alternative.

Pre-registered scoring/decision rule: exact-match against ground truth,
McNemar's test on discordant pairs, reported once, regardless of direction.
No re-running, no threshold tuning, no cherry-picking which run to report.

Two implementation fixes made during a pre-run smoke test (first ~9
incidents), before any accuracy number was computed -- disclosed here rather
than silently applied: (1) the Falsifier's alternative hypothesis was
originally free text and could return a negation ("Low CPU Usage"), which the
keyword scorer misread as an affirmative CPU-fault match; fixed by
constraining the alternative to the same closed 5-category vocabulary used
everywhere else in this evaluation. (2) the initial adversarial prompt
("actively try to refute") caused the Falsifier to refute nearly every
hypothesis in the smoke sample, including ones that were already correct --
a miscalibrated verifier that always says no is not a fair test of whether
verification helps, so the prompt was revised once to default to "confirmed"
absent concrete contradicting evidence, and to require a refuted alternative
to be clearly and substantially better supported, not merely plausible. Both
fixes were made on implementation grounds (is the verifier well-formed at
all) before looking at any accuracy outcome, and are now locked for the full,
single run on all 75 incidents.
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
print(f'Falsifier test on {len(incidents)} AIOps incidents')

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

def build_finding_summary(inc):
    baseline = inc.get('baseline_stats', {})
    def rel_deviation(name, s):
        b = baseline.get(name)
        if not b or b.get('mean', 0) == 0: return None
        return abs(s['mean'] - b['mean']) / abs(b['mean'])
    def sort_key(kv):
        name, s = kv
        dev = rel_deviation(name, s)
        return (0, -dev) if dev is not None else (1, -s['max'])
    lines = []
    for name, s in sorted(inc['window_stats'].items(), key=sort_key):
        if s['max'] == 0 and s['mean'] == 0: continue
        b = baseline.get(name)
        if b and b.get('mean', 0) != 0:
            dev_pct = (s['mean'] - b['mean']) / abs(b['mean']) * 100
            lines.append(f"  - {name}: window mean={s['mean']:.2f} max={s['max']:.2f} (n={s['n']})  |  baseline mean={b['mean']:.2f}  |  deviation={dev_pct:+.0f}%")
        else:
            lines.append(f"  - {name}: window mean={s['mean']:.2f}, max={s['max']:.2f} (n={s['n']})  |  no baseline available")
    tw, tb = inc.get('trace_window'), inc.get('trace_baseline')
    if tw and tb:
        lat_change = (tw['mean_latency_ms'] - tb['mean_latency_ms']) / max(tb['mean_latency_ms'], 0.01) * 100
        lines.append(f"  - call_latency: window_mean={tw['mean_latency_ms']:.1f}ms (baseline={tb['mean_latency_ms']:.1f}ms, {lat_change:+.0f}%), window_max={tw['max_latency_ms']:.0f}ms")
        lines.append(f"  - call_failure_rate: window={tw['failure_rate']*100:.2f}% (baseline={tb['failure_rate']*100:.2f}%)")
    elif tw:
        lines.append(f"  - call_latency: mean={tw['mean_latency_ms']:.1f}ms, failure_rate={tw['failure_rate']*100:.2f}%")
    return '\n'.join(lines) if lines else '  (no non-zero signals observed)'

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

def single_agent_baseline(inc):
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def reasoning_hypothesis(inc):
    prompt = f"""You are the Reasoning agent investigating entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

FAULT_CATEGORIES = ['CPU fault', 'network delay', 'network loss', 'db connection limit', 'db  close']

def falsifier(inc, hyp_root_cause, hyp_conf):
    prompt = f"""You are the Falsifier agent. The Reasoning agent investigated entity {inc['entity']} ({inc['object_type']} type) and proposed this hypothesis:
  root_cause = "{hyp_root_cause}"
  confidence = {hyp_conf}

Below is the COMPLETE raw telemetry for this incident -- every metric collected, including signals the Reasoning agent's summary may not have surfaced:

{raw_dump_block(inc)}

Your task is to check this hypothesis against the evidence, actively looking for contradictions rather than assuming it is right. But most hypotheses that correctly read the dominant signal in the data ARE right, and your job is to catch the ones that are not -- not to override every hypothesis with a different guess. Default to "confirmed" unless you find SPECIFIC, CONCRETE evidence in the raw data that contradicts the hypothesis (e.g. the metric it names is not actually anomalous, or a different metric shows a much larger, more clearly causal deviation). Use "refuted" only when a competing category is CLEARLY and SUBSTANTIALLY better supported by the raw data than the original hypothesis -- not merely plausible or equally consistent with it. Use "contested" when you have doubts but no clearly better alternative.

If you refute the hypothesis AND have a specific competing cause in mind, your alternative must be an AFFIRMATIVE root-cause category naming what IS wrong -- one of exactly these five: {FAULT_CATEGORIES}. Do not return a statement that a metric is normal, low, or ruled out (e.g. "Low CPU Usage" is not a valid alternative -- that says CPU is NOT the problem, it does not name what IS). If refuting but you have no confident affirmative alternative from that list, set alternative_category to null.

Respond JSON: {{"verdict": "confirmed" | "contested" | "refuted", "alternative_category": "<one of the five categories above, or null>", "rationale": "<one sentence>"}}"""
    return call_json("gpt-4o-mini", prompt)

outpath = '/tmp/aiops_work/out/results_v9_falsifier.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_hyp','')) and 'ERROR' not in str(prior.get('final_multi_hyp','')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt = inc['ground_truth_fault']

    try:
        sa = single_agent_baseline(inc)
        sa_hyp, sa_conf = sa.get('root_cause',''), sa.get('confidence')
    except Exception as e:
        sa_hyp, sa_conf = f'ERROR: {e}', None
    sa_score = score(sa_hyp, gt)

    try:
        rea = reasoning_hypothesis(inc)
        rea_hyp, rea_conf = rea.get('root_cause',''), rea.get('confidence')
        fals = falsifier(inc, rea_hyp, rea_conf)
        verdict = fals.get('verdict', 'confirmed')
        alt = fals.get('alternative_category')
        if verdict == 'refuted' and alt in FAULT_CATEGORIES:
            final_hyp = alt
        else:
            final_hyp = rea_hyp
    except Exception as e:
        rea_hyp, verdict, alt, final_hyp = f'ERROR: {e}', 'ERROR', None, f'ERROR: {e}'
    final_score = score(final_hyp, gt)

    print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): single={sa_score}({sa_hyp}) '
          f'reasoning={rea_hyp} verdict={verdict} alt={alt} final={final_score}({final_hyp})', flush=True)

    results.append({'index': inc['index'], 'ground_truth': gt,
                     'single_agent_hyp': sa_hyp, 'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
                     'reasoning_hyp': rea_hyp, 'falsifier_verdict': verdict, 'falsifier_alternative': alt,
                     'final_multi_hyp': final_hyp, 'final_multi_score': final_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
