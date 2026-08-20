# Response to Reviewers — NetOpsAgent (CNSM 2026 Revision)

We thank the reviewers for pushing us on evaluation rigor, novelty vs. recent work, and
presentation. This revision responds to every point below.

**1. Evaluation rigor / "data appears prepared" (R3).** The original evaluation (200
traces, 78.5%, p=0.002) is fully replaced. Section V reports six pre-registered
configurations on two real datasets: AIOps Challenge 2020 (N=75) and RCAEval RE1
(N=75, Online Boutique/Sock Shop/Train Ticket). Result: no significant multi-agent
advantage over single-agent on either dataset (p>0.05 throughout); a rule-based
baseline stays competitive. Even the configuration designed to most favor the
architecture (raw-context test) shows the opposite: single-agent beats multi-agent
(25.3% vs. 4.0%, p=0.064), because blind metric-name selection under decomposition
picks generic metrics regardless of the true anomaly (Sec. VI-A). Sec. VI-B discloses
single-run noise explicitly (an unchanged prompt moved 8 points between runs).

**2. Single- vs. multi-agent, with/without RAG (specific request).** Table II reports
the full 2×2 design on both datasets. RAG gives no significant improvement either way
(p=0.55–0.69); both conditions share identical retrieval access.

**3. RAG corpus independence.** Sec. IV-D confirms the 21-chunk retrieval corpus was
authored before evaluation and contains no incident-specific text (real embeddings,
cosine similarity, not a keyword stand-in).

**4. Novelty vs. Flow-of-Action / MA-RCA (R1–2).** We agree NetOpsAgent's decomposition
is not architecturally novel and have narrowed the claim (new Sec. II-G). We also went
further: both comparison systems attribute gains to an added *capability* (executable
SOPs; dynamic validation), not mere decomposition. We built and pre-registered a
Falsifier agent (Sec. III-G) testing an LLM-based proxy for MA-RCA's Validation Agent,
reported regardless of direction (Sec. V-H):

| Condition (N=75) | Single-agent | +Falsifier | p |
|---|---|---|---|
| AIOps, multi-agent+Falsifier | 21.3% | 33.3% | 0.023 |
| AIOps, single-agent+Falsifier (control) | 21.3% | 32.0% | 0.077 |
| RCAEval | 42.7% | 24.0% | <0.001 |
| RCAEval, topology-aware | 42.7% | 40.0% | 0.50 |

The Falsifier helps significantly on single-entity incidents, hurts significantly on
multi-service ones (symptom propagation mistaken for root cause, absent topology
awareness). A real, verified service-topology fix eliminates the regression (p=0.50)
but adds no gain. A pre-registered control then isolated whether the AIOps gain needs
multi-agent decomposition at all: the same Falsifier on the single-agent hypothesis
scores statistically indistinguishably from the multi-agent version (p=1.0
head-to-head). The honest reading: the verification *capability* drives the gain, not
agent count — consistent with two concurrent 2026 papers we now cite (Sec. II-G): Xu et
al. (arXiv:2601.12307) show homogeneous multi-agent workflows are matched by a
well-tuned single agent, and NetOpsAgent's own heterogeneous GPT-4o/GPT-4o-mini split
already tests their proposed necessary condition and still shows no gain; Su & Wu
(arXiv:2602.08272) explain theoretically why decomposition loses its advantage on
interdependent tasks like whole-incident diagnosis. This paper's central claim is now
that a specific capability, not architecture, drives value — a sharper, more current
contribution than the original.

**5. Confidence calibration.** Sec. V-G replaces the original Table III with real data:
verbalized confidence does not discriminate correct from incorrect hypotheses (0.86 vs.
0.85 AIOps; 0.90 vs. 0.87 RCAEval); at the proposed 0.75 gate, 96–100% of incorrect
hypotheses pass. Self-consistency resampling doesn't fix this either (0.98 vs. 0.93) —
the model is often *consistently* wrong. Reported as a genuine safety finding.

**6. Missing references — 13/32 cited (R3).** Fixed: 37 entries, all cited, verified
programmatically.

**7. "Hierarchical" architecture (R3).** Sec. III now walks the pipeline explicitly and
states what makes it hierarchical (supervisor delegation) vs. simple pipelining.

**8. Technical choices — GPT version, thresholds (R4).** All backed by real ablations:
CPU threshold sweep (73.3–81.3%, not sensitive in normal range); GPT-4o vs. mini
(comparable on AIOps, worse on RCAEval, 1/17th cost — now the stated rationale in
Sec. IV-A); RAG relevance gating (modest AIOps gain, wash on RCAEval); confidence-gate
sweep (no threshold works, Sec. V-G).

**9. Figure 1 readability (R3).** Redrawn as a vector diagram.

---

**Summary.** Unchanged: architecture (Sec. III), implementation (Sec. IV). Changed:
evaluation fully replaced with real data; confidence claim replaced with a real
null-discrimination finding; unsupported claims removed; headline result changed from
an inflated positive to an honest null on decomposition plus a precisely-scoped
positive finding (verification capability, independent of agent count); novelty claim
narrowed and positioned against current literature; references fixed (37/37); Figure 1
redrawn; all requested ablations completed with real data. This is a more rigorous
paper than originally submitted — same architecture and motivation, real pre-registered
measurements throughout, and a defensible, fully-reproducible contribution.
