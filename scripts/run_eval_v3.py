import json, os, time
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/incidents_with_trace_v3.json'))
print(f'Running v2 (with real network trace features) on {len(incidents)} incidents')

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
    if any(k in t for k in CATEGORY_KEYWORDS[gt]):
        return 'exact'
    if any(k in t for k in DOMAIN_KW[DOMAIN_OF[gt]]):
        return 'partial'
    return 'incorrect'

def build_finding_summary(inc):
    lines = []
    for name, s in sorted(inc['window_stats'].items(), key=lambda kv: -kv[1]['max']):
        if s['max'] == 0 and s['mean'] == 0:
            continue
        lines.append(f"  - {name}: mean={s['mean']:.2f}, max={s['max']:.2f} (n={s['n']})")
    tw, tb = inc.get('trace_window'), inc.get('trace_baseline')
    if tw and tb:
        lat_change = (tw['mean_latency_ms'] - tb['mean_latency_ms']) / max(tb['mean_latency_ms'], 0.01) * 100
        p95_change = (tw['p95_latency_ms_sampled'] - tb['p95_latency_ms_sampled']) / max(tb['p95_latency_ms_sampled'], 0.01) * 100
        lines.append(f"  - call_latency: window_mean={tw['mean_latency_ms']:.1f}ms (baseline={tb['mean_latency_ms']:.1f}ms, {lat_change:+.0f}%), "
                     f"window_p95={tw['p95_latency_ms_sampled']:.1f}ms (baseline={tb['p95_latency_ms_sampled']:.1f}ms, {p95_change:+.0f}%), "
                     f"window_max={tw['max_latency_ms']:.0f}ms")
        lines.append(f"  - call_failure_rate: window={tw['failure_rate']*100:.2f}% (baseline={tb['failure_rate']*100:.2f}%), n_calls_in_window={tw['n_calls']}")
    elif tw:
        lines.append(f"  - call_latency: mean={tw['mean_latency_ms']:.1f}ms, p95={tw['p95_latency_ms_sampled']:.1f}ms, max={tw['max_latency_ms']:.0f}ms, failure_rate={tw['failure_rate']*100:.2f}%")
    return '\n'.join(lines) if lines else '  (no non-zero signals observed)'

def rule_based(inc):
    stats = inc['window_stats']
    tw, tb = inc.get('trace_window'), inc.get('trace_baseline')
    if inc['entity'].startswith('db'):
        return 'db connection limit'
    if stats.get('container_cpu_used', {}).get('max', 0) > 80:
        return 'CPU fault'
    if tw and tb and tb['failure_rate'] < tw['failure_rate']:
        return 'network loss'
    if tw and tb and tb['mean_latency_ms'] > 0 and tw['p95_latency_ms_sampled'] > 2 * tb['p95_latency_ms_sampled']:
        return 'network delay'
    return 'network delay'

def call_json(model, prompt):
    resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}],
                                           response_format={"type":"json_object"}, temperature=0.2)
    return json.loads(resp.choices[0].message.content)

def single_agent(inc):
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def telemetry_mini(inc):
    prompt = f"""Summarize these raw signals into a short structured findings list (only anomalous/notable signals, ignore flat zero metrics). Entity: {inc['entity']} ({inc['object_type']}).

{build_finding_summary(inc)}"""
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0.2)
    return r.choices[0].message.content

def reasoning(inc, findings):
    prompt = f"""You are the Reasoning agent. The Telemetry agent produced these findings for entity {inc['entity']} ({inc['object_type']}):

{findings}

Determine the most likely root cause based ONLY on these findings. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

outpath = '/tmp/aiops_work/out/results_v3.json'
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
    rb_hyp = rule_based(inc); rb_score = score(rb_hyp, gt)
    try:
        sa = single_agent(inc); sa_hyp, sa_conf = sa.get('root_cause',''), sa.get('confidence')
    except Exception as e:
        sa_hyp, sa_conf = f'ERROR: {e}', None
    sa_score = score(sa_hyp, gt)
    try:
        findings = telemetry_mini(inc)
        ma = reasoning(inc, findings); ma_hyp, ma_conf = ma.get('root_cause',''), ma.get('confidence')
    except Exception as e:
        findings, ma_hyp, ma_conf = f'ERROR: {e}', f'ERROR: {e}', None
    ma_score = score(ma_hyp, gt)
    print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): rb={rb_score} sa={sa_score}({sa_hyp}) ma={ma_score}({ma_hyp})', flush=True)
    results.append({'index': inc['index'], 'ground_truth': gt, 'layer': inc['ground_truth_layer'],
                     'rule_based_hyp': rb_hyp, 'rule_based_score': rb_score,
                     'single_agent_hyp': sa_hyp, 'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
                     'multi_agent_findings': findings, 'multi_agent_hyp': ma_hyp, 'multi_agent_confidence': ma_conf, 'multi_agent_score': ma_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
