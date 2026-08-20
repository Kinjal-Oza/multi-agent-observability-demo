import json, os, sys, time
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI
from rag_retrieval import retrieve

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/incidents_with_trace_v3.json'))
print(f'Running v6-RAG (adds single-agent+RAG and multi-agent+RAG conditions, real embedding retrieval '
      f'over a 21-chunk generic SOP corpus, no incident-specific content) on {len(incidents)} incidents')

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
    baseline = inc.get('baseline_stats', {})
    def rel_deviation(name, s):
        b = baseline.get(name)
        if not b or b.get('mean', 0) == 0:
            return None
        return abs(s['mean'] - b['mean']) / abs(b['mean'])
    def sort_key(kv):
        name, s = kv
        dev = rel_deviation(name, s)
        if dev is not None:
            return (0, -dev)
        return (1, -s['max'])
    lines = []
    for name, s in sorted(inc['window_stats'].items(), key=sort_key):
        if s['max'] == 0 and s['mean'] == 0:
            continue
        b = baseline.get(name)
        if b and b.get('mean', 0) != 0:
            dev_pct = (s['mean'] - b['mean']) / abs(b['mean']) * 100
            lines.append(f"  - {name}: window mean={s['mean']:.2f} max={s['max']:.2f} (n={s['n']})  |  baseline mean={b['mean']:.2f}  |  deviation={dev_pct:+.0f}%")
        else:
            lines.append(f"  - {name}: window mean={s['mean']:.2f}, max={s['max']:.2f} (n={s['n']})  |  no baseline available")
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

def call_json(model, prompt):
    resp = client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}],
                                           response_format={"type":"json_object"}, temperature=0.2)
    return json.loads(resp.choices[0].message.content)

def retrieved_block(inc):
    query = f"entity {inc['entity']} ({inc['object_type']}):\n{build_finding_summary(inc)}"
    hits = retrieve(query, k=5)
    return '\n'.join(f'  [{i+1}] {h}' for i, h in enumerate(hits))

def single_agent_rag(inc):
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary(inc)}

Retrieved operational knowledge (top-5, from a generic SRE runbook corpus, not specific to this incident):

{retrieved_block(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def telemetry_mini(inc):
    prompt = f"""Summarize these raw signals into a short structured findings list (only anomalous/notable signals, ignore flat zero metrics). Entity: {inc['entity']} ({inc['object_type']}).

{build_finding_summary(inc)}"""
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":prompt}], temperature=0.2)
    return r.choices[0].message.content

def reasoning_rag(inc, findings):
    prompt = f"""You are the Reasoning agent. The Telemetry agent produced these findings for entity {inc['entity']} ({inc['object_type']}):

{findings}

For reference, here is the raw signal data the Telemetry agent was summarizing:

{build_finding_summary(inc)}

Retrieved operational knowledge (top-5, from a generic SRE runbook corpus, not specific to this incident):

{retrieved_block(inc)}

Determine the most likely root cause, using the raw signal data as the primary source of truth. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

outpath = '/tmp/aiops_work/out/results_v6_rag.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_rag_hyp','')) and 'ERROR' not in str(prior.get('multi_agent_rag_hyp','')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt = inc['ground_truth_fault']
    try:
        sa = single_agent_rag(inc); sa_hyp, sa_conf = sa.get('root_cause',''), sa.get('confidence')
    except Exception as e:
        sa_hyp, sa_conf = f'ERROR: {e}', None
    sa_score = score(sa_hyp, gt)
    try:
        findings = telemetry_mini(inc)
        ma = reasoning_rag(inc, findings); ma_hyp, ma_conf = ma.get('root_cause',''), ma.get('confidence')
    except Exception as e:
        findings, ma_hyp, ma_conf = f'ERROR: {e}', f'ERROR: {e}', None
    ma_score = score(ma_hyp, gt)
    print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): sa_rag={sa_score}({sa_hyp}) ma_rag={ma_score}({ma_hyp})', flush=True)
    results.append({'index': inc['index'], 'ground_truth': gt, 'layer': inc['ground_truth_layer'],
                     'single_agent_rag_hyp': sa_hyp, 'single_agent_rag_confidence': sa_conf, 'single_agent_rag_score': sa_score,
                     'multi_agent_rag_findings': findings, 'multi_agent_rag_hyp': ma_hyp, 'multi_agent_rag_confidence': ma_conf, 'multi_agent_rag_score': ma_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
