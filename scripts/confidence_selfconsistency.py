"""Self-consistency confidence ablation.

Pre-registered design (written before running, not tuned to outcome):
- Sample the final root-cause call 5x at temperature=0.7 (diversity) instead
  of once at 0.2.
- New "confidence" = fraction of the 5 samples that land in the same
  CATEGORY_KEYWORDS bucket as the plurality answer (self-consistency rate).
- Final hypothesis = the plurality-vote answer's first occurrence.
- Compare: does self-consistency rate separate correct from incorrect
  better than the original single-shot verbalized confidence did (which we
  already showed doesn't discriminate at all: 59.9% base rate vs 60.4% at
  any reasonable gate)?
- Run on a fixed-size, non-cherry-picked sample (first 30 incidents) of each
  dataset to keep cost bounded; report N clearly, don't extrapolate beyond it.
"""
import json, sys
from collections import Counter
sys.path.insert(0, '/tmp/aiops_work')
from openai import OpenAI

env = {}
for line in open('/tmp/secrets/openai.env'):
    k, v = line.strip().split('=', 1)
    env[k] = v
client = OpenAI(api_key=env['OPENAI_API_KEY'], timeout=30.0, max_retries=1)

SAMPLE_N = 30
N_SAMPLES = 5
TEMP = 0.7

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

def bucket(hyp, gt):
    # which CATEGORY_KEYWORDS bucket (of all 5 fault types) does this guess best match, for voting
    t = hyp.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return 'other'

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
        p95_change = (tw['p95_latency_ms_sampled'] - tb['p95_latency_ms_sampled']) / max(tb['p95_latency_ms_sampled'], 0.01) * 100
        lines.append(f"  - call_latency: window_mean={tw['mean_latency_ms']:.1f}ms (baseline={tb['mean_latency_ms']:.1f}ms, {lat_change:+.0f}%), "
                     f"window_p95={tw['p95_latency_ms_sampled']:.1f}ms (baseline={tb['p95_latency_ms_sampled']:.1f}ms, {p95_change:+.0f}%), "
                     f"window_max={tw['max_latency_ms']:.0f}ms")
        lines.append(f"  - call_failure_rate: window={tw['failure_rate']*100:.2f}% (baseline={tb['failure_rate']*100:.2f}%), n_calls_in_window={tw['n_calls']}")
    elif tw:
        lines.append(f"  - call_latency: mean={tw['mean_latency_ms']:.1f}ms, p95={tw['p95_latency_ms_sampled']:.1f}ms, max={tw['max_latency_ms']:.0f}ms, failure_rate={tw['failure_rate']*100:.2f}%")
    return '\n'.join(lines) if lines else '  (no non-zero signals observed)'

def sample_hyps(prompt, n=N_SAMPLES):
    import time
    hyps = []
    for _ in range(n):
        for attempt in range(4):
            try:
                resp = client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":prompt}],
                                                       response_format={"type":"json_object"}, temperature=TEMP)
                d = json.loads(resp.choices[0].message.content)
                hyps.append(d.get('root_cause',''))
                break
            except Exception as e:
                if attempt == 3:
                    hyps.append(f'ERROR: {e}')
                else:
                    time.sleep(3 * (attempt + 1))
    return hyps

incidents = json.load(open('/tmp/aiops_work/out/incidents_with_trace_v3.json'))[:SAMPLE_N]
print(f'Self-consistency confidence ablation: N={len(incidents)} incidents, {N_SAMPLES} samples/incident, temp={TEMP}')

outpath = '/tmp/aiops_work/out/selfconsistency_aiops.json'
try:
    existing = {r['index']: r for r in json.load(open(outpath))}
except FileNotFoundError:
    existing = {}
results = list(existing.values())

for n, inc in enumerate(incidents):
    if inc['index'] in existing:
        print(f'[{n+1}/{len(incidents)}] {inc["index"]} skip', flush=True); continue
    gt = inc['ground_truth_fault']
    prompt = f"""You are an SRE investigating an infrastructure incident on entity {inc['entity']} ({inc['object_type']} type). Raw signals from a 20-minute window around the alert, compared to a baseline period:

{build_finding_summary(inc)}

Determine the most likely root cause. Respond JSON: {{"root_cause": "<short label>"}}"""
    hyps = sample_hyps(prompt)
    buckets = [bucket(h, gt) for h in hyps]
    plurality_bucket, plurality_count = Counter(buckets).most_common(1)[0]
    sc_confidence = plurality_count / len(hyps)
    final_hyp = next(h for h, b in zip(hyps, buckets) if b == plurality_bucket)
    final_score = score(final_hyp, gt)
    print(f'[{n+1}/{len(incidents)}] {inc["index"]} ({gt}): samples={hyps} -> final={final_hyp} sc_conf={sc_confidence:.2f} score={final_score}', flush=True)
    results.append({'index': inc['index'], 'ground_truth': gt, 'samples': hyps, 'buckets': buckets,
                     'final_hyp': final_hyp, 'sc_confidence': sc_confidence, 'score': final_score})
    json.dump(results, open(outpath, 'w'), indent=2)

print('DONE')
