import zipfile, csv, json, io, datetime
from collections import defaultdict

DAY_ZIPS = {
    '2020_04_11': '/tmp/aiops_work/AIOps挑战赛数据/2020_04_11.zip',
    '2020_04_20': '/tmp/aiops_raw_days/2020_04_20.zip',
    '2020_04_21': '/tmp/aiops_raw_days/2020_04_21.zip',
    '2020_04_22': '/tmp/aiops_raw_days/2020_04_22.zip',
    '2020_04_23': '/tmp/aiops_work/AIOps挑战赛数据/2020_04_23.zip',
    '2020_05_22': '/tmp/aiops_work/AIOps挑战赛数据/2020_05_22.zip',
    '2020_05_23': '/tmp/aiops_raw_days/2020_05_23.zip',
    '2020_05_24': '/tmp/aiops_raw_days/2020_05_24.zip',
    '2020_05_25': '/tmp/aiops_raw_days/2020_05_25.zip',
    '2020_05_26': '/tmp/aiops_raw_days/2020_05_26.zip',
    '2020_05_27': '/tmp/aiops_raw_days/2020_05_27.zip',
    '2020_05_28': '/tmp/aiops_raw_days/2020_05_28.zip',
    '2020_05_29': '/tmp/aiops_raw_days/2020_05_29.zip',
    '2020_05_30': '/tmp/aiops_raw_days/2020_05_30.zip',
    '2020_05_31': '/tmp/aiops_raw_days/2020_05_31.zip',
}
PWD = '这是挑战赛初赛答案密码'.encode('utf-8')
TRACE_FILES = ['trace_csf.csv', 'trace_osb.csv', 'trace_remote_process.csv',
               'trace_fly_remote.csv', 'trace_jdbc.csv', 'trace_local.csv']

incidents = json.load(open('/tmp/aiops_work/out/incidents_v3.json'))
usable = [i for i in incidents if i['window_metric_count'] > 0 and i['baseline_metric_count'] > 0]
print(f'{len(usable)} incidents with robust window+baseline (feeding trace enrichment)')

CST = datetime.timezone(datetime.timedelta(hours=8))
def to_epoch_ms(datestr):
    dt = datetime.datetime.strptime(datestr, '%Y/%m/%d %H:%M').replace(tzinfo=CST)
    return int(dt.timestamp() * 1000)

WINDOW_MS = 20 * 60 * 1000
BASELINE_LO, BASELINE_HI = WINDOW_MS, 4 * WINDOW_MS

# build lookup: (day_dir, entity) -> list of (incident_index, fault_ts)
targets = defaultdict(list)
for inc in usable:
    targets[(inc['day_dir'], inc['entity'])].append((inc['index'], to_epoch_ms(inc['effective_time'])))

class Agg:
    __slots__ = ('n', 'sum_e', 'max_e', 'fails', 'sample')
    def __init__(self):
        self.n = 0; self.sum_e = 0.0; self.max_e = 0.0; self.fails = 0; self.sample = []
    def add(self, elapsed, ok):
        self.n += 1; self.sum_e += elapsed
        if elapsed > self.max_e: self.max_e = elapsed
        if not ok: self.fails += 1
        if len(self.sample) < 2000:
            self.sample.append(elapsed)
    def to_dict(self):
        if self.n == 0: return None
        s = sorted(self.sample)
        p95 = s[int(len(s)*0.95)] if s else self.max_e
        return {'n_calls': self.n, 'mean_latency_ms': self.sum_e/self.n, 'max_latency_ms': self.max_e,
                'p95_latency_ms_sampled': p95, 'failure_rate': self.fails/self.n, 'n_failures': self.fails}

window_agg = defaultdict(Agg)
baseline_agg = defaultdict(Agg)

days_needed = sorted(set(inc['day_dir'] for inc in usable))
print('days to stream:', days_needed)

for day_dir in days_needed:
    zpath = DAY_ZIPS[day_dir]
    z = zipfile.ZipFile(zpath)
    for tf in TRACE_FILES:
        member = f'{day_dir}/调用链指标/{tf}'
        try:
            info = z.getinfo(member)
        except KeyError:
            continue
        print(f'streaming {member} ({info.file_size/1e6:.0f} MB)...', flush=True)
        # try without password first, fall back to password if needed
        try:
            raw_ctx = z.open(member)
            raw_ctx.read(4)
            raw_ctx.close()
            raw = z.open(member)
        except RuntimeError:
            raw = z.open(member, pwd=PWD)
        with raw:
            wrapper = io.TextIOWrapper(raw, encoding='utf-8', errors='replace')
            reader = csv.DictReader(wrapper)
            for row in reader:
                cmdb = row.get('cmdb_id')
                key = (day_dir, cmdb)
                if key not in targets:
                    continue
                try:
                    ts = int(row['startTime'])
                    elapsed = float(row['elapsedTime'])
                    ok = row['success'] == 'True'
                except (ValueError, KeyError):
                    continue
                for inc_idx, fault_ts in targets[key]:
                    d = ts - fault_ts
                    if abs(d) <= WINDOW_MS:
                        window_agg[inc_idx].add(elapsed, ok)
                    elif BASELINE_LO < d <= BASELINE_HI or -BASELINE_HI <= d < -BASELINE_LO:
                        baseline_agg[inc_idx].add(elapsed, ok)

for inc in usable:
    idx = inc['index']
    inc['trace_window'] = window_agg[idx].to_dict() if idx in window_agg else None
    inc['trace_baseline'] = baseline_agg[idx].to_dict() if idx in baseline_agg else None

json.dump(usable, open('/tmp/aiops_work/out/incidents_with_trace_v3.json', 'w'), indent=2)
print('DONE.')
with_trace = sum(1 for i in usable if i.get('trace_window'))
print(f'{with_trace}/{len(usable)} incidents got trace-window enrichment')
