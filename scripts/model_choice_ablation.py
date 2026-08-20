import json, sys
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

CATEGORY_KEYWORDS = {
    'CPU fault': ['cpu'],
    'network delay': ['network delay', 'latency', 'delay', 'slow network', 'network slow'],
    'network loss': ['network loss', 'packet loss', 'loss', 'connection drop', 'dropped'],
    'db connection limit': ['connection limit', 'connection pool', 'too many connection', 'session limit'],
    'db  close': ['db close', 'database down', 'connection closed', 'db unavailable', 'database unreachable'],
}
DOMAIN_KW = {'cpu': ['cpu', 'compute'], 'network': ['network', 'connectivity', 'latency', 'packet'], 'db': ['database', 'db ', 'sql', 'connection']}
DOMAIN_OF = {'CPU fault':'cpu','network delay':'network','network loss':'network','db connection limit':'db','db  close':'db'}

def score_aiops(hyp, gt):
    t = hyp.lower()
    if any(k in t for k in CATEGORY_KEYWORDS[gt]): return 'exact'
    if any(k in t for k in DOMAIN_KW[DOMAIN_OF[gt]]): return 'partial'
    return 'incorrect'

def build_finding_summary_aiops(inc):
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

def single_agent_aiops(inc, model):
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary_aiops(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>", "confidence": <0-1>}}"""
    return call_json(model, prompt)

# --- RCAEval scoring/prompt (reuse) ---
FAULT_TYPE_KEYWORDS = {
    'CPU fault': ['cpu'], 'memory fault': ['memory', 'mem ', ' mem', 'oom', 'ram'],
    'disk fault': ['disk', 'i/o', 'io ', 'storage'],
    'network loss': ['packet loss', 'loss', 'connection drop', 'dropped', 'error rate', 'errors'],
    'network delay': ['delay', 'latency', 'slow network', 'network delay'],
}
DOMAIN_KW2 = {
    'CPU fault': ['cpu', 'compute'], 'memory fault': ['memory', 'mem'], 'disk fault': ['disk', 'storage', 'i/o'],
    'network loss': ['network', 'loss', 'error', 'connectivity'], 'network delay': ['network', 'latency', 'delay', 'connectivity'],
}
def score_rca(guess_service, guess_fault, gt_service, gt_fault):
    svc_txt = (guess_service or '').lower()
    fault_txt = (guess_fault or '').lower()
    svc_match = gt_service.lower() in svc_txt or svc_txt in gt_service.lower() if svc_txt else False
    fault_exact = any(k in fault_txt for k in FAULT_TYPE_KEYWORDS.get(gt_fault, []))
    fault_domain = any(k in fault_txt for k in DOMAIN_KW2.get(gt_fault, []))
    if svc_match and fault_exact: return 'exact'
    if svc_match or fault_domain: return 'partial'
    return 'incorrect'

TOP_N = 12
def top_services(inc, n=TOP_N):
    scores = inc['svc_scores']
    return [s for s, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:n]]

def build_finding_summary_rca(inc):
    svcs = top_services(inc)
    lines = []
    for svc in svcs:
        metrics = inc['by_service_metric'].get(svc, {})
        metric_lines = []
        for metric, wb in sorted(metrics.items()):
            w, b = wb['window'], wb['baseline']
            if not w: continue
            if b and b.get('mean', 0) not in (0, None):
                dev_pct = (w['mean'] - b['mean']) / abs(b['mean']) * 100
                metric_lines.append(f"{metric}: window_mean={w['mean']:.3g} baseline_mean={b['mean']:.3g} deviation={dev_pct:+.0f}%")
            else:
                metric_lines.append(f"{metric}: window_mean={w['mean']:.3g} (no baseline)")
        if metric_lines:
            lines.append(f"- service '{svc}': " + '; '.join(metric_lines))
    return '\n'.join(lines) if lines else '(no anomalous services detected)'

def single_agent_rca(inc, model):
    prompt = f"""You are an SRE investigating a production incident in a microservice system ({inc['system']}). Below are the {TOP_N} services with the most anomalous telemetry in the incident window vs. a pre-incident baseline:

{build_finding_summary_rca(inc)}

Identify the most likely ROOT CAUSE SERVICE and FAULT TYPE. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json(model, prompt)


def run_aiops(model, outpath):
    incidents = json.load(open('/tmp/aiops_work/out/incidents_with_trace_v3.json'))
    try:
        existing = {r['index']: r for r in json.load(open(outpath))}
    except FileNotFoundError:
        existing = {}
    results = list(existing.values())
    for n, inc in enumerate(incidents):
        if inc['index'] in existing and 'ERROR' not in str(existing[inc['index']].get('hyp','')):
            print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip', flush=True); continue
        if inc['index'] in existing: results.remove(existing[inc['index']])
        gt = inc['ground_truth_fault']
        try:
            r = single_agent_aiops(inc, model); hyp, conf = r.get('root_cause',''), r.get('confidence')
        except Exception as e:
            hyp, conf = f'ERROR: {e}', None
        s = score_aiops(hyp, gt)
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): {s}({hyp})', flush=True)
        results.append({'index': inc['index'], 'ground_truth': gt, 'hyp': hyp, 'confidence': conf, 'score': s})
        json.dump(results, open(outpath, 'w'), indent=2)

def run_rca(model, outpath):
    incidents = json.load(open('/tmp/aiops_work/out/rcaeval_incidents.json'))
    try:
        existing = {r['index']: r for r in json.load(open(outpath))}
    except FileNotFoundError:
        existing = {}
    results = list(existing.values())
    for n, inc in enumerate(incidents):
        if inc['index'] in existing and 'ERROR' not in str(existing[inc['index']].get('service','')):
            print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip', flush=True); continue
        if inc['index'] in existing: results.remove(existing[inc['index']])
        gt_svc, gt_fault = inc['ground_truth_service'], inc['ground_truth_fault']
        try:
            r = single_agent_rca(inc, model)
            svc, fault, conf = r.get('root_cause_service',''), r.get('fault_type',''), r.get('confidence')
        except Exception as e:
            svc, fault, conf = f'ERROR: {e}', f'ERROR: {e}', None
        s = score_rca(svc, fault, gt_svc, gt_fault)
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} (gt={gt_svc}/{gt_fault}): {s}({svc}/{fault})', flush=True)
        results.append({'index': inc['index'], 'ground_truth_service': gt_svc, 'ground_truth_fault': gt_fault,
                         'service': svc, 'fault': fault, 'confidence': conf, 'score': s})
        json.dump(results, open(outpath, 'w'), indent=2)

if __name__ == '__main__':
    which = sys.argv[1]  # 'aiops' or 'rca'
    model = sys.argv[2]  # 'gpt-4o' or 'gpt-4o-mini'
    outpath = sys.argv[3]
    if which == 'aiops':
        run_aiops(model, outpath)
    else:
        run_rca(model, outpath)
    print('DONE')
