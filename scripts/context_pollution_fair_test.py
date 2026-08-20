"""Fair test of the paper's actual "context pollution" hypothesis.

Every prior run (v3-v7) gave BOTH single-agent and multi-agent the same
pre-ranked, pre-filtered, deviation-annotated summary -- i.e. neither one
ever tested what the paper claims causes single-agent failure: a single
agent drowning in raw, undigested, unranked telemetry. This script builds
that fair test:

  - single_agent_raw_dump: gets EVERY metric (including flat/zero ones,
    unsorted, no deviation annotation, no filtering) plus full raw trace
    dicts. This is deliberately the least-processed context -- true
    "context pollution" as the paper describes it.
  - multi_agent_iterative: Telemetry Agent first sees only metric NAMES
    (no values), picks up to 8 to inspect, then receives full stats
    (with deviation annotation, same processing as v5) for exactly those
    metrics plus trace data, and produces structured findings. Reasoning
    Agent gets only those findings (not the raw dump) -- true
    "context hygiene via decomposition" as the paper describes it.

Pre-registered before running: if the paper's hypothesis is right, this
should be the condition most likely to show a real multi-agent advantage,
since it's the first time either baseline has actually tested it. Report
whatever happens.
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
print(f'Fair context-pollution test on {len(incidents)} incidents')

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
    t = hyp.lower()
    if any(k in t for k in CATEGORY_KEYWORDS[gt]): return 'exact'
    if any(k in t for k in DOMAIN_KW[DOMAIN_OF[gt]]): return 'partial'
    return 'incorrect'

def call_json(model, prompt):
    resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}],
                                           response_format={"type":"json_object"}, temperature=0.2)
    return json.loads(resp.choices[0].message.content)

def raw_dump_block(inc):
    # EVERYTHING, unsorted (dict iteration order), unfiltered, no deviation math.
    lines = []
    for name, s in inc['window_stats'].items():
        lines.append(f"  - {name}: window(mean={s['mean']:.2f}, max={s['max']:.2f}, min={s['min']:.2f}, n={s['n']})")
    for name, s in inc['baseline_stats'].items():
        lines.append(f"  - {name}_baseline: (mean={s['mean']:.2f}, max={s['max']:.2f}, min={s['min']:.2f}, n={s['n']})")
    tw, tb = inc.get('trace_window'), inc.get('trace_baseline')
    if tw:
        lines.append(f"  - trace_window_raw: {tw}")
    if tb:
        lines.append(f"  - trace_baseline_raw: {tb}")
    return '\n'.join(lines)

def single_agent_raw_dump(inc):
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Below is the complete, unfiltered raw telemetry captured for this incident -- every metric collected, in no particular order, including ones that may be irrelevant:

{raw_dump_block(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def build_finding_summary_for(inc, metric_names):
    baseline = inc.get('baseline_stats', {})
    lines = []
    for name in metric_names:
        s = inc['window_stats'].get(name)
        if not s: continue
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
    return '\n'.join(lines) if lines else '  (no data for selected metrics)'

def telemetry_select(inc):
    names = sorted(inc['window_stats'].keys())
    prompt = f"""You are the Telemetry Investigation Agent for entity {inc['entity']} ({inc['object_type']} type). Here are the names of every metric collected for this incident (values withheld):

{names}

Pick up to 8 metric names you most want to inspect closely to diagnose this incident. Respond JSON: {{"selected_metrics": ["name1", "name2", ...]}}"""
    r = call_json("gpt-4o-mini", prompt)
    sel = r.get('selected_metrics', [])
    return [m for m in sel if m in inc['window_stats']][:8]

def telemetry_investigate(inc, selected):
    prompt = f"""You are the Telemetry Investigation Agent. You selected these metrics to inspect for entity {inc['entity']} ({inc['object_type']}):

{build_finding_summary_for(inc, selected)}

Summarize your findings (only anomalous/notable signals)."""
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0.2)
    return r.choices[0].message.content

def reasoning_iterative(inc, findings):
    prompt = f"""You are the Reasoning agent. The Telemetry agent investigated entity {inc['entity']} ({inc['object_type']}) and produced these findings:

{findings}

Determine the most likely root cause based on these findings. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

outpath = '/tmp/aiops_work/out/results_v8_context_fair.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_hyp','')) and 'ERROR' not in str(prior.get('multi_agent_hyp','')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt = inc['ground_truth_fault']
    try:
        sa = single_agent_raw_dump(inc); sa_hyp, sa_conf = sa.get('root_cause',''), sa.get('confidence')
    except Exception as e:
        sa_hyp, sa_conf = f'ERROR: {e}', None
    sa_score = score(sa_hyp, gt)
    try:
        selected = telemetry_select(inc)
        findings = telemetry_investigate(inc, selected)
        ma = reasoning_iterative(inc, findings); ma_hyp, ma_conf = ma.get('root_cause',''), ma.get('confidence')
    except Exception as e:
        selected, findings, ma_hyp, ma_conf = [], f'ERROR: {e}', f'ERROR: {e}', None
    ma_score = score(ma_hyp, gt)
    print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): raw_single={sa_score}({sa_hyp}) iter_multi={ma_score}({ma_hyp}) selected={selected}', flush=True)
    results.append({'index': inc['index'], 'ground_truth': gt,
                     'single_agent_hyp': sa_hyp, 'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
                     'selected_metrics': selected, 'multi_agent_findings': findings,
                     'multi_agent_hyp': ma_hyp, 'multi_agent_confidence': ma_conf, 'multi_agent_score': ma_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
