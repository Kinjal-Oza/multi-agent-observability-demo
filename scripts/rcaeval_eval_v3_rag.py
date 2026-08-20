import json, sys
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI
from rag_retrieval import retrieve

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/rcaeval_incidents.json'))
print(f'Running RCAEval RE1 v3-RAG (adds single-agent+RAG and multi-agent+RAG, same 21-chunk generic '
      f'SOP corpus as AIOps v6) on {len(incidents)} independent fault-injection scenarios')

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


def call_json(model, prompt):
    resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                           response_format={"type": "json_object"}, temperature=0.2)
    return json.loads(resp.choices[0].message.content)


def retrieved_block(inc):
    query = f"microservice system {inc['system']} incident:\n{build_finding_summary(inc)}"
    hits = retrieve(query, k=5)
    return '\n'.join(f'  [{i+1}] {h}' for i, h in enumerate(hits))


def single_agent_rag(inc):
    prompt = f"""You are an SRE investigating a production incident in a microservice system ({inc['system']}). Below are the {TOP_N} services with the most anomalous telemetry in the incident window vs. a pre-incident baseline:

{build_finding_summary(inc)}

Retrieved operational knowledge (top-5, from a generic SRE runbook corpus, not specific to this incident):

{retrieved_block(inc)}

Identify the most likely ROOT CAUSE SERVICE and FAULT TYPE. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)


def telemetry_mini(inc):
    prompt = f"""Summarize this multi-service telemetry deviation report into a short structured findings list, highlighting the most anomalous service(s) and what metric(s) are abnormal. System: {inc['system']}.

{build_finding_summary(inc)}"""
    r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.2)
    return r.choices[0].message.content


def reasoning_rag(inc, findings):
    prompt = f"""You are the Reasoning agent. The Telemetry agent produced these findings for a microservice incident in system {inc['system']}:

{findings}

For reference, here is the raw per-service deviation data the Telemetry agent was summarizing:

{build_finding_summary(inc)}

Retrieved operational knowledge (top-5, from a generic SRE runbook corpus, not specific to this incident):

{retrieved_block(inc)}

Determine the most likely ROOT CAUSE SERVICE and FAULT TYPE, using the raw data as the primary source of truth. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)


outpath = '/tmp/aiops_work/out/rcaeval_results_v3_rag.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_rag_hyp', '')) and 'ERROR' not in str(prior.get('multi_agent_rag_hyp', '')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt_svc, gt_fault = inc['ground_truth_service'], inc['ground_truth_fault']

    try:
        sa = single_agent_rag(inc)
        sa_svc, sa_fault, sa_conf = sa.get('root_cause_service', ''), sa.get('fault_type', ''), sa.get('confidence')
    except Exception as e:
        sa_svc, sa_fault, sa_conf = f'ERROR: {e}', f'ERROR: {e}', None
    sa_score = score(sa_svc, sa_fault, gt_svc, gt_fault)

    try:
        findings = telemetry_mini(inc)
        ma = reasoning_rag(inc, findings)
        ma_svc, ma_fault, ma_conf = ma.get('root_cause_service', ''), ma.get('fault_type', ''), ma.get('confidence')
    except Exception as e:
        findings, ma_svc, ma_fault, ma_conf = f'ERROR: {e}', f'ERROR: {e}', f'ERROR: {e}', None
    ma_score = score(ma_svc, ma_fault, gt_svc, gt_fault)

    print(f'[{n+1}/{len(incidents)}] {inc["index"]} (gt={gt_svc}/{gt_fault}): '
          f'sa_rag={sa_score}({sa_svc}/{sa_fault}) ma_rag={ma_score}({ma_svc}/{ma_fault})', flush=True)

    results.append({
        'index': inc['index'], 'system': inc['system'],
        'ground_truth_service': gt_svc, 'ground_truth_fault': gt_fault,
        'single_agent_rag_service': sa_svc, 'single_agent_rag_fault': sa_fault, 'single_agent_rag_confidence': sa_conf, 'single_agent_rag_score': sa_score,
        'multi_agent_rag_findings': findings, 'multi_agent_rag_service': ma_svc, 'multi_agent_rag_fault': ma_fault,
        'multi_agent_rag_confidence': ma_conf, 'multi_agent_rag_score': ma_score,
    })
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
