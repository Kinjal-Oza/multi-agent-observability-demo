import csv, json, datetime, os
from collections import defaultdict

METRICS_DIR = '/tmp/aiops_work/metrics'
FAULT_CSV = '/tmp/aiops_meta/故障整理（预赛）.csv'

# All 15 days now extracted.
AVAILABLE_DAYS = {
    '2020/4/11': '2020_04_11',
    '2020/4/20': '2020_04_20',
    '2020/4/21': '2020_04_21',
    '2020/4/22': '2020_04_22',
    '2020/4/23': '2020_04_23',
    '2020/5/22': '2020_05_22',
    '2020/5/23': '2020_05_23',
    '2020/5/24': '2020_05_24',
    '2020/5/25': '2020_05_25',
    '2020/5/26': '2020_05_26',
    '2020/5/27': '2020_05_27',
    '2020/5/28': '2020_05_28',
    '2020/5/29': '2020_05_29',
    '2020/5/30': '2020_05_30',
    '2020/5/31': '2020_05_31',
}

OBJECT_TO_FILE = {
    'docker': 'dcos_docker.csv',
    'os': 'os_linux.csv',
    'db': 'db_oracle_11g.csv',
}

LAYER_MAP = {
    'network delay': 'network',
    'network loss': 'network',
    'CPU fault': 'infrastructure',
    'db connection limit': 'application',
    'db  close': 'application',
}

CST = datetime.timezone(datetime.timedelta(hours=8))

def to_epoch_ms(datestr):
    dt = datetime.datetime.strptime(datestr, '%Y/%m/%d %H:%M').replace(tzinfo=CST)
    return int(dt.timestamp() * 1000)

rows = list(csv.DictReader(open(FAULT_CSV, encoding='utf-8')))
print(f'Total ground-truth fault records: {len(rows)}')

# CORRECTED FIELD SELECTION:
# index 1-11: start_time is empty -> the real fault date/time is log_time.
# index 100-169: start_time is populated with the true fault date/time
#   (matches the daily zip folder names exactly); log_time for these rows
#   is a stale/mismatched field carried over from a different context and
#   must NOT be used for date bucketing.
def effective_time(r):
    st = r['start_time'].strip()
    return st if st else r['log_time'].strip()

target = []
skipped_no_data_release = []
for r in rows:
    t = effective_time(r)
    day = t.split(' ')[0]
    if day in AVAILABLE_DAYS:
        target.append((r, t))
    else:
        skipped_no_data_release.append((r['index'], day))

print(f'{len(target)} of {len(rows)} incidents fall on a day we have telemetry for')
print(f'{len(skipped_no_data_release)} fall on days never publicly released: '
      f'{sorted(set(d for _, d in skipped_no_data_release))}')

def load_metric_index(day_dir, filename):
    path = f'{METRICS_DIR}/{day_dir}__{filename}'
    idx = defaultdict(list)
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx[row['cmdb_id']].append((int(row['timestamp']), row['name'], row['value']))
    return idx

cache = {}
def get_index(day_dir, obj_type):
    key = (day_dir, obj_type)
    if key not in cache:
        cache[key] = load_metric_index(day_dir, OBJECT_TO_FILE[obj_type])
    return cache[key]

incidents = []
WINDOW_MS = 20 * 60 * 1000
for r, t in target:
    day_dir = AVAILABLE_DAYS[t.split(' ')[0]]
    obj_type = r['object']
    cmdb_id = r['name']
    fault_ts = to_epoch_ms(t)

    idx = get_index(day_dir, obj_type)
    series = idx.get(cmdb_id, [])
    windowed = [(ts, name, val) for ts, name, val in series if abs(ts - fault_ts) <= WINDOW_MS]
    baseline_window = [(ts, name, val) for ts, name, val in series if fault_ts - ts > WINDOW_MS and fault_ts - ts <= 4*WINDOW_MS]

    def stats_by_metric(pts):
        by_metric = defaultdict(list)
        for ts, name, val in pts:
            try:
                by_metric[name].append(float(val))
            except ValueError:
                pass
        out = {}
        for name, vals in by_metric.items():
            if vals:
                out[name] = {'mean': sum(vals)/len(vals), 'max': max(vals), 'min': min(vals), 'n': len(vals)}
        return out

    window_stats = stats_by_metric(windowed)
    baseline_stats = stats_by_metric(baseline_window)

    incidents.append({
        'index': r['index'],
        'ground_truth_fault': r['fault_desrcibtion'].strip(),
        'ground_truth_layer': LAYER_MAP.get(r['fault_desrcibtion'].strip(), 'unknown'),
        'object_type': obj_type,
        'entity': cmdb_id,
        'kpi_hint': r['kpi'],
        'effective_time': t,
        'day_dir': day_dir,
        'window_metric_count': len(windowed),
        'baseline_metric_count': len(baseline_window),
        'window_stats': window_stats,
        'baseline_stats': baseline_stats,
    })

os.makedirs('/tmp/aiops_work/out', exist_ok=True)
with open('/tmp/aiops_work/out/incidents_v3.json', 'w') as f:
    json.dump(incidents, f, indent=2)

nonzero = [i for i in incidents if i['window_metric_count'] > 0]
zero = [i for i in incidents if i['window_metric_count'] == 0]
print('Incidents with non-empty window data:', len(nonzero))
print('Incidents with ZERO window data (entity not found in metrics):', len(zero))
from collections import Counter
print('layer distribution (nonzero):', Counter(i['ground_truth_layer'] for i in nonzero))
