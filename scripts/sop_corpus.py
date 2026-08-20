# Generic operational-knowledge corpus for the RAG condition.
#
# Written from general SRE/networking domain knowledge, independent of any
# specific incident in AIOps Challenge 2020 or RCAEval. Nothing here
# references a specific service name, entity ID, timestamp, or dataset --
# these are the kind of procedural chunks a real ops team's runbook/wiki
# would contain regardless of which incidents end up in any benchmark.
# This is what makes the "no overlap with evaluation traces" claim
# trivially true and verifiable: the corpus was fixed BEFORE evaluation
# and contains no incident-identifying information at all.

SOP_CHUNKS = [
    # --- CPU ---
    "CPU saturation runbook: when CPU utilization on a host or container sustains above 80-90% "
    "for several minutes, check for a runaway process, a stuck retry loop, GC thrashing on a JVM "
    "service, or an undersized autoscaling group. Correlate with request rate -- if CPU rises "
    "without a matching traffic increase, suspect an inefficient code path or a recent deploy.",
    "CPU throttling in containerized environments: if a container has a CPU limit set and usage "
    "approaches that limit, the kernel cgroup throttles it, which manifests as increased latency "
    "even though raw CPU percentage looks capped rather than spiking. Distinguish true saturation "
    "from throttling by checking cgroup throttled_time alongside usage.",
    "Postmortem pattern -- CPU: incidents with a sudden, sustained rise in CPU mean/max on a single "
    "host, with other metrics (memory, network, disk) flat, are almost always resolved by identifying "
    "and restarting or scaling the offending process; root cause is host/process-local, not network.",

    # --- memory ---
    "Memory exhaustion runbook: gradual, monotonic growth in RSS/heap usage over the incident window "
    "with no corresponding drop is the signature of a memory leak; a sudden step-change is usually a "
    "large batch job, cache warm-up, or a spike in concurrent connections each holding a buffer.",
    "OOM and GC pressure: services approaching their memory limit often show increased latency before "
    "an outright crash, because garbage collection pauses lengthen as available heap shrinks. If "
    "latency and memory both trend upward together with CPU flat, suspect memory pressure over CPU.",
    "Postmortem pattern -- memory: memory-fault incidents are frequently mis-attributed to CPU because "
    "GC activity consumes CPU cycles as a side effect; check whether CPU rise correlates with memory "
    "growth (memory-driven) or is independent of it (CPU-driven).",

    # --- disk ---
    "Disk I/O bottleneck runbook: elevated read/write latency, growing I/O queue depth, or increasing "
    "disk utilization percentage indicate a storage-layer bottleneck. This often surfaces indirectly "
    "as elevated application-level call latency or timeouts, since disk metrics are not always "
    "exported at the same granularity as CPU/memory/network.",
    "Diagnosing disk faults without direct disk telemetry: when disk I/O metrics aren't available, "
    "look for a service whose CPU and memory are both flat/normal but whose call latency and error "
    "rate are elevated -- this pattern, by elimination, is consistent with an I/O-bound bottleneck "
    "(disk or otherwise) rather than a compute-bound one.",
    "Postmortem pattern -- disk: disk-fault incidents on database or storage-tier services often present "
    "as slow queries or connection timeouts rather than an obvious disk metric spike, because the "
    "application layer surfaces the symptom before the storage layer's own metrics do.",

    # --- network delay ---
    "Network delay runbook: a rise in p95/p99 latency without a corresponding rise in error/failure "
    "rate typically points to added network delay (congestion, route change, added hop) rather than "
    "packet loss. Compare mean vs p95 -- delay-type incidents widen the tail more than the mean.",
    "Distinguishing network delay from compute slowness: if downstream call latency rises while the "
    "local service's own CPU/memory stay flat, the added latency is most likely in the network path "
    "or in a dependency, not in local processing.",
    "Postmortem pattern -- network delay: incidents where call latency (mean and p95) both rise "
    "sharply relative to baseline, with failure rate roughly unchanged, are consistent with network "
    "delay; this is the most reliably detectable fault type from latency telemetry alone.",

    # --- network loss ---
    "Network packet loss runbook: packet loss manifests as an increased failure/error rate and often "
    "increased retries, which can paradoxically show up as flat or even reduced mean latency for "
    "successful calls (since failed calls return fast) alongside a clear rise in error rate.",
    "Distinguishing loss from delay: network loss primarily moves the failure-rate/error-rate metric; "
    "network delay primarily moves the latency metric. When both shift only modestly but failure rate "
    "shows the largest relative deviation of any signal, favor a loss-type diagnosis.",
    "Postmortem pattern -- network loss: connection-drop and packet-loss incidents are frequently "
    "under-detected by agents that focus only on the largest-magnitude metric, because the failure-rate "
    "delta is often smaller in absolute terms than a co-occurring but unrelated CPU or latency metric.",

    # --- db / connection-limit ---
    "Database connection pool exhaustion runbook: when a service's connection pool hits its configured "
    "limit, new requests queue or fail immediately with connection errors; the database host itself "
    "may show normal CPU/memory while the application-side error rate spikes.",
    "DB unavailability runbook: an abrupt database outage typically causes correlated failures across "
    "every downstream service that depends on it, with the DB host's own metrics showing either a "
    "hard drop to zero (process down) or a sustained spike in active session/connection count.",
    "Postmortem pattern -- database: entities whose name or role indicates a database/storage "
    "component, combined with an elevated session or connection-count metric relative to baseline, are "
    "the strongest signal for a DB-layer root cause versus compute or network layers.",

    # --- general triage ---
    "General incident triage: prioritize the metric with the largest RELATIVE deviation from its own "
    "baseline, not the largest absolute value -- a metric that is naturally large but stable (e.g. "
    "steady-state tablespace usage) is less informative than one that moved sharply from its own norm.",
    "General incident triage: when multiple services show anomalous telemetry simultaneously, the true "
    "root cause is usually the service whose anomaly appears earliest in the window and is most severe "
    "in relative terms; downstream services often show secondary, smaller deviations as a cascade "
    "effect rather than being the origin.",
    "General incident triage: root-cause hypotheses should be stated in terms of the affected resource "
    "dimension (CPU, memory, disk, network delay, network loss, database) rather than vague phrases "
    "like 'performance degradation', since downstream remediation steps differ substantially by "
    "resource dimension.",
]

if __name__ == '__main__':
    print(f'{len(SOP_CHUNKS)} SOP chunks authored')
    for c in SOP_CHUNKS:
        assert len(c) < 600, 'keep chunks short/summary-like'
    print('OK')
