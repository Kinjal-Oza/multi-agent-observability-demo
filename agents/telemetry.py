"""Telemetry investigation agent.

Given an investigation context, query the (mock) observability stack and
return structured findings. Does not interpret. Only collects.

The agent has access to a bounded set of tools. Bounded tool sets mean the
agent can't hallucinate a tool that doesn't exist — every tool call goes
through schema-validated entry points.
"""
from __future__ import annotations

from agents.state import AgentStep, Finding, InvestigationState
from tools.deploy_log_mock import recent_deploys
from tools.logs_mock import search_logs
from tools.prometheus_mock import query_metric


def telemetry_step(state: InvestigationState) -> InvestigationState:
    """Gather findings from configured telemetry sources."""
    trigger = state["trigger"]
    findings: list[Finding] = state.get("telemetry_findings", [])

    # 1. Pull the metric that fired the alert, plus its neighbourhood.
    metric_result = query_metric(
        service=trigger.service,
        metric=trigger.metric,
        window_minutes=15,
    )
    findings.append(Finding(
        source="prometheus",
        description=f"{trigger.metric} on {trigger.service}: {metric_result['summary']}",
        severity="warning" if metric_result["anomaly"] else "info",
        raw=metric_result,
    ))

    # 2. Pull related-dependency metrics if any anomaly suggests we should.
    if metric_result["anomaly"]:
        for dep in metric_result.get("dependencies", []):
            dep_result = query_metric(service=dep, metric="utilization", window_minutes=15)
            findings.append(Finding(
                source="prometheus",
                description=f"dependency {dep} utilization: {dep_result['summary']}",
                severity="warning" if dep_result["anomaly"] else "info",
                raw=dep_result,
            ))

    # 3. Pull recent deploys for the service.
    deploys = recent_deploys(service=trigger.service, window_minutes=60)
    for d in deploys:
        findings.append(Finding(
            source="deploy_log",
            description=f"deploy: {d['service']} {d['version']} at {d['deployed_at']}",
            severity="info",
            raw=d,
        ))

    # 4. Pull error logs in the window.
    log_hits = search_logs(service=trigger.service, window_minutes=15, level_at_least="ERROR")
    if log_hits:
        findings.append(Finding(
            source="logs",
            description=f"{len(log_hits)} ERROR log entries in window",
            severity="warning",
            raw={"hits": log_hits},
        ))

    state["telemetry_findings"] = findings
    state["audit_trail"].append(AgentStep(
        agent="telemetry",
        description=f"Collected {len(findings)} findings from {sum(1 for f in findings if f.severity != 'info')} anomalous sources",
    ))
    return state
