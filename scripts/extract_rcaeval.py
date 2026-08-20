import zipfile, csv, json, io
from collections import defaultdict

ZIP_PATH = '/tmp/rcaeval_re1.zip'
RUN = '1'   # use ONE run per unique (system, service, fault-type) scenario.
            # RCAEval provides 6 repeated runs per scenario; those repeats are
            # correlated replicates of the identical injected fault, not
            # independent incidents, so averaging/pooling all 6 into N would
            # be pseudoreplication. Using run 1 for every scenario gives
            # N = one real, independent case per unique fault condition.
            # (All 6 runs remain on disk for anyone who wants a replication
            # check later.)

FAULT_TYPE_MAP = {
    'cpu': 'CPU fault',
    'mem': 'memory fault',
    'disk': 'disk fault',
    'loss': 'network loss',
    'delay': 'network delay',
}

z = zipfile.ZipFile(ZIP_PATH)
names = z.namelist()

# discover all (system, case_dir) with the chosen RUN present.
# Some scenarios ship BOTH simple_data.csv (preprocessed) and data.csv (raw) --
# prefer simple_data.csv when both exist, so each scenario is counted once.
by_case = {}
for n in names:
    parts = n.split('/')
    if len(parts) == 5 and parts[0] == 'RE1' and parts[3] == RUN and parts[4] in ('simple_data.csv', 'data.csv'):
        sys_dir, case_dir, run, fname = parts[1], parts[2], parts[3], parts[4]
        key = (sys_dir, case_dir)
        if key in by_case and by_case[key]['fname'] == 'simple_data.csv':
            continue  # already have the preferred file for this scenario
        service, fault_suffix = case_dir.rsplit('_', 1)
        by_case[key] = {'sys_dir': sys_dir, 'case_dir': case_dir, 'service': service,
                         'fault_suffix': fault_suffix, 'fname': fname,
                         'path': n, 'inject_path': f'RE1/{sys_dir}/{case_dir}/{run}/inject_time.txt'}
cases = list(by_case.values())

print(f'{len(cases)} unique scenarios found for run={RUN}')
from collections import Counter
print('by system:', Counter(c['sys_dir'] for c in cases))
print('by fault:', Counter(c['fault_suffix'] for c in cases))


def parse_simple(raw_bytes):
    """TT / SS format: single 'time' column, DictReader-safe."""
    text = raw_bytes.decode('utf-8', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    metric_cols = [c for c in reader.fieldnames if c != 'time']
    series = defaultdict(list)  # metric_col -> list of (ts, val)
    for r in rows:
        try:
            ts = int(float(r['time']))
        except (ValueError, TypeError):
            continue
        for c in metric_cols:
            v = r.get(c)
            if v in (None, ''):
                continue
            try:
                series[c].append((ts, float(v)))
            except ValueError:
                pass
    return series


def parse_ob(raw_bytes):
    """OB format: TWO columns literally named 'time' (metrics block + error
    block), which collide under DictReader. Parse positionally instead."""
    text = raw_bytes.decode('utf-8', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    header = rows[0]
    time_idxs = [i for i, h in enumerate(header) if h == 'time']
    primary_time_idx = time_idxs[0]
    metric_idxs = [(i, h) for i, h in enumerate(header) if h != 'time']
    series = defaultdict(list)
    for r in rows[1:]:
        if len(r) <= primary_time_idx:
            continue
        try:
            ts = int(float(r[primary_time_idx]))
        except ValueError:
            continue
        for i, colname in metric_idxs:
            if i >= len(r) or r[i] == '':
                continue
            try:
                series[colname].append((ts, float(r[i])))
            except ValueError:
                pass
    return series


def stats(pairs):
    if not pairs:
        return None
    vals = [v for _, v in pairs]
    return {'mean': sum(vals) / len(vals), 'max': max(vals), 'min': min(vals), 'n': len(vals)}


incidents = []
for c in cases:
    inject_ts = int(float(z.read(c['inject_path']).decode().strip()))
    raw = z.read(c['path'])
    if c['fname'] == 'simple_data.csv':
        series = parse_simple(raw)
    else:
        series = parse_ob(raw)

    # group columns by service: "{service}_{metric}"
    by_service_metric = defaultdict(dict)  # service -> metric -> {'window':.., 'baseline':..}
    for col, pairs in series.items():
        svc, metric = col.rsplit('_', 1)
        window_pairs = [(t, v) for t, v in pairs if t >= inject_ts]
        baseline_pairs = [(t, v) for t, v in pairs if t < inject_ts]
        w = stats(window_pairs)
        b = stats(baseline_pairs)
        by_service_metric[svc][metric] = {'window': w, 'baseline': b}

    # relative deviation per service (max across its metrics with a computable baseline)
    svc_scores = {}
    for svc, metrics in by_service_metric.items():
        best = 0.0
        for metric, wb in metrics.items():
            w, b = wb['window'], wb['baseline']
            if w and b and b['mean'] not in (0, None):
                dev = abs(w['mean'] - b['mean']) / abs(b['mean'])
                if dev > best:
                    best = dev
        svc_scores[svc] = best

    incidents.append({
        'index': f"{c['sys_dir']}/{c['case_dir']}/{RUN}",
        'system': c['sys_dir'],
        'ground_truth_service': c['service'],
        'ground_truth_fault_suffix': c['fault_suffix'],
        'ground_truth_fault': FAULT_TYPE_MAP[c['fault_suffix']],
        'inject_ts': inject_ts,
        'by_service_metric': by_service_metric,
        'svc_scores': svc_scores,
    })
    print(f"  parsed {c['sys_dir']}/{c['case_dir']} services={len(by_service_metric)}", flush=True)

import os
os.makedirs('/tmp/aiops_work/out', exist_ok=True)
with open('/tmp/aiops_work/out/rcaeval_incidents.json', 'w') as f:
    json.dump(incidents, f)
print('DONE. wrote', len(incidents), 'incidents')
