> **Superseded.** This was a drafting aid from before the paper's Related Work §II-G was
> finalized. It does not include the Falsifier control test or the two 2026 citations
> (Xu et al., Su & Wu) now in the actual paper. See the paper itself for current text.

# Related work positioning (for paper + rebuttal)

## The two works reviewers cited

**Pei et al., "Flow-of-Action: SOP Enhanced LLM-Based Multi-Agent System for Root Cause
Analysis"** (ACM Web Conference 2025 companion). Main agent + auxiliary agents (noise
removal, search-space narrowing, termination assessment). SOP-centric: retrieves SOPs,
generates new ones when none exist, converts SOPs to executable code. Reports 64.01%
accuracy vs. 35.50% for a ReAct baseline.

**Fu et al., "Leveraging multi-agent framework for root cause analysis"** (Complex &
Intelligent Systems, 2026; also called MA-RCA). Specialized agents including a Retrieval
Agent (RAG over historical documentation) and a Validation Agent (dynamic testing against
runtime data). Evaluated on Nezha (cloud-native platforms, 95.2% F1) and a distributed
power-metering dataset (82.8% F1).

## Honest novelty assessment

Both papers already explore: (1) decomposing RCA into specialized LLM agents, and (2)
grounding agent hypotheses in retrieved external/historical knowledge. NetOpsAgent's
Telemetry Agent + Reasoning Agent + RAG design is a similar decomposition, not a
different architectural family. The paper cannot honestly claim architectural novelty
over these two works. That claim should be removed or sharply narrowed.

## What NetOpsAgent can honestly claim instead

An empirical result, not an architectural first: on two independent, real, fault-injection
benchmarks (AIOps Challenge 2020, N=75 usable incidents; RCAEval RE1, N=75 independent
scenarios), with a disclosed, generic, pre-registered RAG corpus (21 chunks, zero
incident-specific content, embedded with text-embedding-3-small, real cosine retrieval),
we found:

- No significant single-vs-multi-agent difference on either dataset (McNemar p=0.39 and
  p=1.0 for the no-RAG condition; p=0.51 and p=0.69 with RAG added).
- No significant benefit from adding RAG to either architecture on either dataset.
- A simple rule-based baseline matches or beats both LLM-based architectures on AIOps.

This is a useful negative/null result given Flow-of-Action's and Fu et al.'s much larger
reported gains: it suggests the benefit of multi-agent decomposition and retrieval
augmentation for this task is highly setup-dependent (dataset, corpus, scoring
granularity) rather than a general property of the architecture family. That is the
paper's real, defensible contribution if it goes forward: a controlled empirical
comparison, not a new SOTA claim.

This is a materially smaller claim than the original submission made. It should be
stated plainly in the rebuttal, not softened.
