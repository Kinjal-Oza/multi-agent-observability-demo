"""Pre-registered follow-up to falsifier_test_rcaeval.py: does giving the
Falsifier real service-topology awareness fix the symptom-propagation
regression found there?

Rationale, written before running: the v1 Falsifier test on RCAEval showed a
significant regression (42.7%->24.0%, p<0.001) because, inspecting the actual
broken cases, it repeatedly overrode a correct root-cause service with a
*different* service that was also anomalous in the same window -- a
downstream victim of propagation, not an independent cause. The fix tested
here: give the Falsifier the real, published service dependency graph for
each system (service_topology.py; verified against each project's own
documentation, not memory alone) and instruct it that two graph-connected
services being simultaneously anomalous is expected propagation, not
independent evidence -- it should only override with a graph-connected
alternative if that alternative's OWN direct resource metric (cpu/mem/disk,
not latency/error-rate, which can be inherited from a dependency) shows a
stronger, more direct match to the fault category than the original
hypothesis's service. Non-graph-connected alternatives are judged as before.

Scope disclosed: Online Boutique and Sock Shop get the real, verified call
graph. Train Ticket (64 services in our data, not feasible to hand-verify a
full call graph from available sources) gets only the naming-convention rule
(ts-X-mongo/-mysql is X's own datastore) -- a partial fix for TT, not a full
one.

To isolate exactly one change and avoid introducing new sampling noise into
parts of the pipeline that are not being tested, this script REUSES the
already-computed single-agent and Reasoning-agent outputs from
rcaeval_results_v5_falsifier.json (same incidents, same run) and re-runs only
the Falsifier step with the topology-aware prompt. Run once, scored once,
reported regardless of direction -- including if it does not fully fix the
regression, which is expected for Train Ticket given the disclosed partial
scope above.
"""
import json, sys
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI
from service_topology import is_connected

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

incidents = json.load(open('/tmp/aiops_work/out/rcaeval_incidents.json'))
prior_results = {r['index']: r for r in json.load(open('/tmp/aiops_work/out/rcaeval_results_v5_falsifier.json'))}
print(f'Topology-aware Falsifier re-test on {len(incidents)} RCAEval RE1 scenarios')

FAULT_TYPE_KEYWORDS = {
    'CPU fault': ['cpu'],
    'memory fault': ['memory', 'mem ', ' mem', 'oom', 'ram'],
    'disk fault': ['disk', 'i/o', 'io ', 'storage'],
    'network loss': ['packet loss', 'loss', 'connection drop', 'dropped', 'error rate', 'errors'],
    'network delay': ['delay', 'latency', 'slow network', 'network delay'],
}
DOMAIN_KW = {
    'CPU fault': ['cpu', 'compute'], 'memory fault': ['memory', 'mem'], 'disk fault': ['disk', 'storage', 'i/o'],
    'network loss': ['network', 'loss', 'error', 'connectivity'], 'network delay': ['network', 'latency', 'delay', 'connectivity'],
}

def score(guess_service, guess_fault, gt_service, gt_fault):
    svc_txt = (guess_service or '').lower(); fault_txt = (guess_fault or '').lower()
    svc_match = gt_service.lower() in svc_txt or svc_txt in gt_service.lower() if svc_txt else False
    fault_exact = any(k in fault_txt for k in FAULT_TYPE_KEYWORDS.get(gt_fault, []))
    fault_domain = any(k in fault_txt for k in DOMAIN_KW.get(gt_fault, []))
    if svc_match and fault_exact: return 'exact'
    if svc_match or fault_domain: return 'partial'
    return 'incorrect'

def build_finding_summary(inc, svcs):
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

def falsifier_topo(inc, hyp_svc, hyp_fault, hyp_conf):
    all_svcs = list(inc['by_service_metric'].keys())
    system = inc['system']
    connected = [s for s in all_svcs if s != hyp_svc and is_connected(system, hyp_svc, s)]
    topo_note = (f"The following services are DIRECTLY connected to '{hyp_svc}' in this system's real service "
                 f"dependency graph (caller/callee of it): {connected if connected else '(none known)'}. "
                 f"A connected service being anomalous at the same time as '{hyp_svc}' is EXPECTED propagation "
                 f"(one calls the other), not independent evidence of a different root cause. Only propose one of "
                 f"these connected services as your alternative if ITS OWN direct resource metric (cpu, mem, or "
                 f"disk -- not latency or error rate, which can simply be inherited from a dependency) shows a "
                 f"stronger, more direct match to a fault category than '{hyp_svc}' does. Services NOT in this "
                 f"list are independent candidates and can be judged normally.")
    prompt = f"""You are the Falsifier agent. The Reasoning agent investigated system {system} and proposed this hypothesis:
  root_cause_service = "{hyp_svc}"
  fault_type = "{hyp_fault}"
  confidence = {hyp_conf}

{topo_note}

Below is telemetry for ALL {len(all_svcs)} services in this system, window vs. baseline:

{build_finding_summary(inc, all_svcs)}

Your task is to check this hypothesis against the evidence, actively looking for contradictions rather than assuming it is right. But most hypotheses that correctly read the dominant signal in the data ARE right, and your job is to catch the ones that are not -- not to override every hypothesis with a different guess, and not to be fooled by expected propagation to a connected service. Default to "confirmed" unless you find SPECIFIC, CONCRETE evidence that contradicts the hypothesis. Use "refuted" only when a competing service/fault-type is CLEARLY and SUBSTANTIALLY better supported by the data than the original. Use "contested" when you have doubts but no clearly better alternative.

Respond JSON: {{"verdict": "confirmed" | "contested" | "refuted", "alternative_service": "<service name or null>", "alternative_fault": "<one of the 5 types, or null>", "rationale": "<one sentence>"}}"""
    return call_json("gpt-4o-mini", prompt)

outpath = '/tmp/aiops_work/out/rcaeval_results_v6_falsifier_topo.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    idx = inc['index']
    prior_new = existing.get(idx)
    if prior_new and 'ERROR' not in str(prior_new.get('final_multi_fault', '')):
        print(f'[{n+1}/{len(incidents)}] {idx} skip (already OK)', flush=True)
        continue
    if prior_new:
        results.remove(prior_new)
    base = prior_results[idx]
    gt_svc, gt_fault = base['ground_truth_service'], base['ground_truth_fault']
    rea_svc, rea_fault, rea_conf = base['reasoning_service'], base['reasoning_fault'], None

    try:
        fals = falsifier_topo(inc, rea_svc, rea_fault, rea_conf)
        verdict = fals.get('verdict', 'confirmed')
        alt_svc, alt_fault = fals.get('alternative_service'), fals.get('alternative_fault')
        if verdict == 'refuted' and alt_svc and str(alt_svc).lower() not in ('null', 'none', ''):
            final_svc = alt_svc
            final_fault = alt_fault if alt_fault and str(alt_fault).lower() not in ('null', 'none', '') else rea_fault
        else:
            final_svc, final_fault = rea_svc, rea_fault
    except Exception as e:
        verdict, alt_svc, alt_fault = 'ERROR', None, None
        final_svc, final_fault = f'ERROR: {e}', f'ERROR: {e}'
    final_score = score(final_svc, final_fault, gt_svc, gt_fault)

    print(f'[{n+1}/{len(incidents)}] {idx} (gt={gt_svc}/{gt_fault}): single={base["single_agent_score"]} '
          f'reasoning={rea_svc}/{rea_fault} verdict={verdict} alt={alt_svc}/{alt_fault} final={final_score}({final_svc}/{final_fault})', flush=True)

    results.append({'index': idx, 'system': inc['system'], 'ground_truth_service': gt_svc, 'ground_truth_fault': gt_fault,
                     'single_agent_score': base['single_agent_score'],
                     'reasoning_service': rea_svc, 'reasoning_fault': rea_fault,
                     'falsifier_verdict': verdict, 'falsifier_alt_service': alt_svc, 'falsifier_alt_fault': alt_fault,
                     'final_multi_service': final_svc, 'final_multi_fault': final_fault, 'final_multi_score': final_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
