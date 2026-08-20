import json
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/rcaeval_incidents.json'))
print(f'Running RCAEval RE1 v2 (architecture fix: Reasoning agent gets raw deviation data + mini-summary) '
      f'on {len(incidents)} independent fault-injection scenarios')

TOP_N = 12

FAULT_TYPE_KEYWORDS = {
    'CPU fault': ['cpu'],
    'memory fault': ['memory', 'mem ', ' mem', 'oom', 'ram'],
    'disk fault': ['disk', 'i/o', 'io ', 'storage'],
    'network loss': ['packet loss', 'loss', 'connection drop', 'dropped', 'error rate', 'errors'],
    'network delay': ['delay', 'latency', 'slow network', 'network delay'],
}
DOMAIN_KW = {
    'CPU fault': ['cpu', 'compute'],
    'memory fault': ['memory', 'mem'],
    'disk fault': ['disk', 'storage', 'i/o'],
    'network loss': ['network', 'loss', 'error', 'connectivity'],
    'network delay': ['network', 'latency', 'delay', 'connectivity'],
}


def score(guess_service, guess_fault, gt_service, gt_fault):
    svc_txt = (guess_service or '').lower()
    fault_txt = (guess_fault or '').lower()
    svc_match = gt_service.lower() in svc_txt or svc_txt in gt_service.lower() if svc_txt else False
    fault_exact = any(k in fault_txt for k in FAULT_TYPE_KEYWORDS.get(gt_fault, []))
    fault_domain = any(k in fault_txt for k in DOMAIN_KW.get(gt_fault, []))
    if svc_match and fault_exact:
        return 'exact'
    if svc_match or fault_domain:
        return 'partial'
    return 'incorrect'


def top_services(inc, n=TOP_N):
    scores = inc['svc_scores']
    return [s for s, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:n]]


def build_finding_summary(inc):
    svcs = top_services(inc)
    lines = []
    for svc in svcs:
        metrics = inc['by_service_metric'].get(svc, {})
        metric_lines = []
        for metric, wb in sorted(metrics.items()):
            w, b = wb['window'], wb['baseline']
            if not w:
                continue
            if b and b.get('mean', 0) not in (0, None):
                dev_pct = (w['mean'] - b['mean']) / abs(b['mean']) * 100
                metric_lines.append(f"{metric}: window_mean={w['mean']:.3g} baseline_mean={b['mean']:.3g} deviation={dev_pct:+.0f}%")
            else:
                metric_lines.append(f"{metric}: window_mean={w['mean']:.3g} (no baseline)")
        if metric_lines:
            lines.append(f"- service '{svc}': " + '; '.join(metric_lines))
    return '\n'.join(lines) if lines else '(no anomalous services detected)'


def rule_based(inc):
    svcs = top_services(inc, n=1)
    if not svcs:
        return None, 'network delay'
    svc = svcs[0]
    metrics = inc['by_service_metric'].get(svc, {})
    best_metric, best_dev = None, -1
    for metric, wb in metrics.items():
        w, b = wb['window'], wb['baseline']
        if w and b and b.get('mean', 0) not in (0, None):
            dev = abs(w['mean'] - b['mean']) / abs(b['mean'])
            if dev > best_dev:
                best_dev, best_metric = dev, metric
    if best_metric == 'cpu':
        fault = 'CPU fault'
    elif best_metric == 'mem':
        fault = 'memory fault'
    elif best_metric in ('workload', 'load'):
        fault = 'network delay'
    elif best_metric and best_metric.startswith('latency'):
        fault = 'network delay'
    elif best_metric == 'error':
        fault = 'network loss'
    else:
        fault = 'disk fault'  # elimination default: RE1 metrics-only subset has no direct disk I/O column
    return svc, fault


def call_json(model, prompt):
    resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                           response_format={"type": "json_object"}, temperature=0.2)
    return json.loads(resp.choices[0].message.content)


def single_agent(inc):
    prompt = f"""You are an SRE investigating a production incident in a microservice system ({inc['system']}). Below are the {TOP_N} services with the most anomalous telemetry in the incident window vs. a pre-incident baseline (ranked by size of deviation):

{build_finding_summary(inc)}

Identify the most likely ROOT CAUSE SERVICE and FAULT TYPE. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)


def telemetry_mini(inc):
    prompt = f"""Summarize this multi-service telemetry deviation report into a short structured findings list, highlighting the most anomalous service(s) and what metric(s) are abnormal. System: {inc['system']}.

{build_finding_summary(inc)}"""
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.2)
    return r.choices[0].message.content


def reasoning(inc, findings):
    # v2 architecture fix (same pre-registered change as AIOps run_eval_v5,
    # applied here for consistency, run once): give the Reasoning agent the
    # raw per-service deviation block as well as the mini-agent's summary,
    # instead of the summary alone.
    prompt = f"""You are the Reasoning agent. The Telemetry agent produced these findings for a microservice incident in system {inc['system']}:

{findings}

For reference, here is the raw per-service deviation data the Telemetry agent was summarizing:

{build_finding_summary(inc)}

Determine the most likely ROOT CAUSE SERVICE and FAULT TYPE, using the raw data as the primary source of truth (the summary above may have dropped or reworded details). Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)


outpath = '/tmp/aiops_work/out/rcaeval_results_v2.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_hyp', '')) and 'ERROR' not in str(prior.get('multi_agent_hyp', '')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt_svc, gt_fault = inc['ground_truth_service'], inc['ground_truth_fault']

    rb_svc, rb_fault = rule_based(inc)
    rb_score = score(rb_svc, rb_fault, gt_svc, gt_fault)

    try:
        sa = single_agent(inc)
        sa_svc, sa_fault, sa_conf = sa.get('root_cause_service', ''), sa.get('fault_type', ''), sa.get('confidence')
    except Exception as e:
        sa_svc, sa_fault, sa_conf = f'ERROR: {e}', f'ERROR: {e}', None
    sa_score = score(sa_svc, sa_fault, gt_svc, gt_fault)

    try:
        findings = telemetry_mini(inc)
        ma = reasoning(inc, findings)
        ma_svc, ma_fault, ma_conf = ma.get('root_cause_service', ''), ma.get('fault_type', ''), ma.get('confidence')
    except Exception as e:
        findings, ma_svc, ma_fault, ma_conf = f'ERROR: {e}', f'ERROR: {e}', f'ERROR: {e}', None
    ma_score = score(ma_svc, ma_fault, gt_svc, gt_fault)

    print(f'[{n+1}/{len(incidents)}] {inc["index"]} (gt={gt_svc}/{gt_fault}): '
          f'rb={rb_score}({rb_svc}/{rb_fault}) sa={sa_score}({sa_svc}/{sa_fault}) ma={ma_score}({ma_svc}/{ma_fault})', flush=True)

    results.append({
        'index': inc['index'], 'system': inc['system'],
        'ground_truth_service': gt_svc, 'ground_truth_fault': gt_fault,
        'rule_based_service': rb_svc, 'rule_based_fault': rb_fault, 'rule_based_score': rb_score,
        'single_agent_service': sa_svc, 'single_agent_fault': sa_fault, 'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
        'multi_agent_findings': findings, 'multi_agent_service': ma_svc, 'multi_agent_fault': ma_fault,
        'multi_agent_confidence': ma_conf, 'multi_agent_score': ma_score,
    })
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
