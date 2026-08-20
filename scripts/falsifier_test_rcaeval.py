"""Pre-registered Falsifier test on RCAEval RE1 -- same design and rationale
as falsifier_test_aiops.py (read that file's docstring for the full
rationale). Mirrors MA-RCA's Validation Agent: a Falsifier (GPT-4o-mini)
checks the Reasoning agent's hypothesis against ALL services' telemetry
(not just the top-N summary Reasoning saw), adversarially, and can override
with a concrete, better-supported alternative. Single-agent baseline is run
fresh in this same script execution for a contemporaneous, paired comparison.
Run once, scored once, reported regardless of direction.
"""
import json, sys
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/rcaeval_incidents.json'))
print(f'Falsifier test on {len(incidents)} RCAEval RE1 scenarios')

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

def build_finding_summary(inc, svcs=None):
    svcs = svcs if svcs is not None else top_services(inc)
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
    import time
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                                   response_format={"type": "json_object"}, temperature=0.2)
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            if 'rate_limit' in str(e).lower() and attempt < 4:
                time.sleep(4 * (attempt + 1))
            else:
                raise

def single_agent_baseline(inc):
    prompt = f"""You are an SRE investigating a production incident in a microservice system ({inc['system']}). Below are the {TOP_N} services with the most anomalous telemetry in the incident window vs. a pre-incident baseline (ranked by size of deviation):

{build_finding_summary(inc)}

Identify the most likely ROOT CAUSE SERVICE and FAULT TYPE. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def reasoning_hypothesis(inc):
    prompt = f"""You are the Reasoning agent investigating a production incident in a microservice system ({inc['system']}). Below are the {TOP_N} services with the most anomalous telemetry in the incident window vs. a pre-incident baseline:

{build_finding_summary(inc)}

Identify the most likely ROOT CAUSE SERVICE and FAULT TYPE. Fault type must be one of: "CPU fault", "memory fault", "disk fault", "network loss", "network delay".
Respond JSON: {{"root_cause_service": "<service name>", "fault_type": "<one of the 5 types>", "confidence": <0-1>}}"""
    return call_json("gpt-4o", prompt)

def falsifier(inc, hyp_svc, hyp_fault, hyp_conf):
    all_svcs = list(inc['by_service_metric'].keys())
    prompt = f"""You are the Falsifier agent. The Reasoning agent investigated system {inc['system']} and proposed this hypothesis:
  root_cause_service = "{hyp_svc}"
  fault_type = "{hyp_fault}"
  confidence = {hyp_conf}

Below is telemetry for ALL {len(all_svcs)} services in this system (not just the top-ranked ones the Reasoning agent used), window vs. baseline:

{build_finding_summary(inc, svcs=all_svcs)}

Your task is to check this hypothesis against the evidence, actively looking for contradictions rather than assuming it is right. But most hypotheses that correctly read the dominant signal in the data ARE right, and your job is to catch the ones that are not -- not to override every hypothesis with a different guess. Default to "confirmed" unless you find SPECIFIC, CONCRETE evidence among the full service telemetry that contradicts the hypothesis. Use "refuted" only when a competing service/fault-type is CLEARLY and SUBSTANTIALLY better supported by the data than the original -- not merely plausible or equally consistent with it. Use "contested" when you have doubts but no clearly better alternative.

Respond JSON: {{"verdict": "confirmed" | "contested" | "refuted", "alternative_service": "<service name or null>", "alternative_fault": "<one of the 5 types, or null>", "rationale": "<one sentence>"}}"""
    return call_json("gpt-4o-mini", prompt)

outpath = '/tmp/aiops_work/out/rcaeval_results_v5_falsifier.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    prior = existing.get(inc['index'])
    if prior and 'ERROR' not in str(prior.get('single_agent_hyp','')) and 'ERROR' not in str(prior.get('final_multi_fault','')):
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip (already OK)', flush=True)
        continue
    if prior:
        results.remove(prior)
    gt_svc, gt_fault = inc['ground_truth_service'], inc['ground_truth_fault']

    try:
        sa = single_agent_baseline(inc)
        sa_svc, sa_fault, sa_conf = sa.get('root_cause_service',''), sa.get('fault_type',''), sa.get('confidence')
    except Exception as e:
        sa_svc, sa_fault, sa_conf = f'ERROR: {e}', f'ERROR: {e}', None
    sa_score = score(sa_svc, sa_fault, gt_svc, gt_fault)

    try:
        rea = reasoning_hypothesis(inc)
        rea_svc, rea_fault = rea.get('root_cause_service',''), rea.get('fault_type','')
        rea_conf = rea.get('confidence')
        fals = falsifier(inc, rea_svc, rea_fault, rea_conf)
        verdict = fals.get('verdict', 'confirmed')
        alt_svc, alt_fault = fals.get('alternative_service'), fals.get('alternative_fault')
        if verdict == 'refuted' and alt_svc and str(alt_svc).lower() not in ('null','none',''):
            final_svc = alt_svc
            final_fault = alt_fault if alt_fault and str(alt_fault).lower() not in ('null','none','') else rea_fault
        else:
            final_svc, final_fault = rea_svc, rea_fault
    except Exception as e:
        rea_svc, rea_fault, verdict, alt_svc, alt_fault = f'ERROR: {e}', f'ERROR: {e}', 'ERROR', None, None
        final_svc, final_fault = f'ERROR: {e}', f'ERROR: {e}'
    final_score = score(final_svc, final_fault, gt_svc, gt_fault)

    print(f'[{n+1}/{len(incidents)}] {inc["index"]} (gt={gt_svc}/{gt_fault}): single={sa_score}({sa_svc}/{sa_fault}) '
          f'reasoning={rea_svc}/{rea_fault} verdict={verdict} alt={alt_svc}/{alt_fault} final={final_score}({final_svc}/{final_fault})', flush=True)

    results.append({'index': inc['index'], 'system': inc['system'],
                     'ground_truth_service': gt_svc, 'ground_truth_fault': gt_fault,
                     'single_agent_service': sa_svc, 'single_agent_fault': sa_fault,
                     'single_agent_confidence': sa_conf, 'single_agent_score': sa_score,
                     'reasoning_service': rea_svc, 'reasoning_fault': rea_fault,
                     'falsifier_verdict': verdict, 'falsifier_alt_service': alt_svc, 'falsifier_alt_fault': alt_fault,
                     'final_multi_service': final_svc, 'final_multi_fault': final_fault, 'final_multi_score': final_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
