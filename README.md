# Travel Customer Support AI — Deployment Case Study

An end-to-end analysis of bringing AI-drafted replies into the customer-support operation of a mid-size travel e-commerce company — scoping, solution design, metrics, and launch gates under data-privacy, system-access, and staffing constraints — plus a runnable PoC of the first rollout stage, ticket triage.

> **Simulated scenario** from a senior field-deployment engineering assignment. The company, stakeholders, and 48 sample tickets are fictional.

## The situation

- About 350 text tickets a day (double in peak season), handled manually by 8 agents
- First response averages 6 hours and often exceeds 24 hours in peak season; complaints are rising
- The support lead wants AI to auto-reply and cut headcount in half
- Customer data may not go to any external service that has not been reviewed, and no LLM provider is contracted
- Order data sits behind an internal API with access review and a low QPS limit; knowledge is scattered across outdated documents

## Key decisions

| Decision | Why |
|---|---|
| **AI triage + drafts with agent review**, not fully automatic replies | Large refunds need supervisor approval, and legal or PR threats need human judgment; a wrong reply costs more than the time saved |
| **Triage by what happens next**: handling path, priority, risk flags | Topic categories do not tell an agent which systems to check or how urgent a ticket is |
| **Code owns business rules; AI owns understanding** | Refund thresholds, departure deadlines, and risk keywords must be deterministic. AI can escalate rule flags but never clear them |
| **Least-privilege tools** | AI requests lookups and code approves them against a per-path ceiling; AI never writes to the order system, which also limits prompt-injection impact |
| **Local open-source model until legal approves a vendor** | Keeps customer data in-house while the vendor review runs in parallel |
| **Staged rollout with rollback by step** | Advisory triage → lookups → drafting, path by path; errors turn off only the failing step |
| **No headcount reduction promised** | Even the best-case 30% handling-time saving leaves peak season over capacity |

## End-to-end workflow

![End-to-end workflow](docs/figures/workflow.png)

Orange is code, purple is AI, blue is human, grey is a system event.

## The PoC: ticket triage, the first rollout stage

Triage ships first because it does not depend on order-API access or curated policy knowledge, and it gets urgent and cross-department tickets handled sooner. The PoC is a runnable triage pipeline over the 48 sample tickets, combining a local `qwen3:8b` model (via Ollama) with deterministic rules.

- **2** tickets archived (spam, test data); **46** enter the support queue
- Of those, **23 (50%)** go to `auto` (AI looks up data and drafts, agent reviews) and **23** to `human`
- **11** tool requests from the model (8 tickets) were blocked by the per-path ceiling, all on human-only paths
- Known gaps are documented, including over-broad urgency flags and tickets where the customer's wording hides the real request

Details, trade-offs, and limitations: [`poc/README.md`](poc/README.md)

## What's inside

| Path | Content |
|---|---|
| [`docs/case-study.md`](docs/case-study.md) | Full analysis: assessment of options, problem definition, solution design, metrics and launch gates, pilot stress test |
| [`poc/`](poc/) | Triage PoC: code, unit tests, sample data, and output |
| [`docs/figures/`](docs/figures/) | Diagrams (Mermaid sources and rendered PNGs) |
