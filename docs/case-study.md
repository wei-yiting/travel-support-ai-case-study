# Bringing AI-Drafted Replies into Travel Customer Support: Deployment Analysis

> **Simulated scenario** from a senior field-deployment engineering assignment. The company, stakeholders, and 48 sample tickets are fictional. This document is the full deployment analysis; the runnable PoC of the first rollout stage, ticket triage, is in [`poc/`](../poc/).

## TL;DR

- **Recommendation:** start with AI triage plus drafted replies that agents review before sending, not fully automatic replies. Treat a standalone knowledge-base Q&A tool as optional, depending on discovery.
- **Triage by what happens next, not by topic:** handling path (which systems and who), priority, and risk flags.
- **Code owns business rules, AI owns understanding:** refund approval thresholds, urgency deadlines, and risk keywords are deterministic; the model can escalate them but never clear them.
- **Least-privilege tools:** the model requests lookups; code approves them against a per-path ceiling. The AI never writes to the order system.
- **Data stays in-house** until legal and security approve an external provider, so the PoC runs on a local open-source model.
- **Staged rollout with explicit gates:** advisory triage → lookups → drafting, path by path, with rollback triggers tied to the stage where an error occurs.
- **Capacity check:** across optimistic and conservative assumptions, AI assistance raises daily capacity from about 360 to roughly 390–480 tickets, well short of about 700 in peak season. There is no basis to promise a headcount reduction.

**What was built vs. designed**

| Scope | Status |
|---|---|
| LLM classification, field extraction, rule merge, and routing | Implemented in the PoC |
| Per-path ceiling on the tools the model requests | Implemented as a filter; the tools themselves are stubs |
| Order API, policy retrieval, drafting, and the agent interface | Designed only |
| Discovery with agents, a labeled evaluation set, and a pilot | Not yet run |

Sections 2–5 are the design; section 6 reports what the PoC showed; section 7 is a hypothetical pilot scenario.

## 1. Context

A mid-size travel e-commerce company receives about 350 text tickets per day by email and web form, roughly double in peak season. Eight agents handle them manually: read, look up systems, reply. Average first response time is 6 hours and often exceeds 24 hours in peak season, and complaints and negative reviews are rising.

| Stakeholder | Position or constraint |
|---|---|
| Support lead | Wants AI to auto-reply and cut headcount in half; estimates 40% order, 30% product, 20% refund or change, 10% other |
| IT | Order system has an internal REST API (lookups, refund requests) behind an access review and a low QPS limit; knowledge is scattered across Word, Excel, and an unmaintained FAQ page; the ticketing system has an API and webhooks |
| Legal and security | Customer personal data must not go to external services that have not been reviewed and contracted; no LLM provider is contracted yet |
| Senior agent | Many tickets require two or three systems; refunds above NT$30,000 need supervisor approval; what customers write often differs from what they need |

The support lead proposed three options:

- **(A)** AI replies to every ticket automatically
- **(B)** AI triages and drafts replies; agents review before sending
- **(C)** An internal knowledge-base Q&A tool for agents

## 2. Assessment

### 2.1 What the sample tickets show

A ticket-by-ticket review of the 48 samples did not match the interview picture:

- Order tickets were clearly below 40%. Complaints, administrative requests (invoices, member accounts), and non-support email made up a large share, so the category definitions need to be revisited with the support lead.
- About 15% were not support tickets at all: job applications, sponsorship pitches, vendor quotes, press requests, and spam.
- About one in six was urgent, for example a typhoon the day before departure, a duplicate charge with a chargeback threat, or threats to go to the consumer protection office or the media.
- One customer included a national ID and bank account number in the email (TK-1023). Another complained that nobody answered the phone but actually wanted the itinerary (TK-1004).

### 2.2 Triage dimensions

Topic categories do not answer "what happens next for this ticket", so triage uses three dimensions:

| Dimension | Definition | Examples |
|---|---|---|
| **Handling path** | Which systems must be checked and who handles it | Needs an order lookup, needs policy knowledge, belongs to another department, non-Chinese (routed to an agent fluent in that language); actual paths come from discovery |
| **Priority** | How urgent | Departing within 72 hours, currently traveling |
| **Risk flags** | Whether to escalate | Amount above NT$30,000, mentions the consumer protection office or the media, contains personal data |

There are also two kinds of knowledge. **Policy knowledge** (change and cancellation rules, standard-contract refund tiers, natural-disaster handling) is relatively stable and can have a named owner. **Product information** (itineraries, prices, inclusions) changes often and should be read from the product system or website directly.

### 2.3 What is still unknown

The interviews did not say which systems agents actually check, how long lookups take, or whether knowledge comes from documents or from asking senior colleagues. The first step is therefore **discovery**: observe agents at work, have senior agents label how sample tickets are handled, and build a baseline from ticketing-system timestamps.

### 2.4 Evaluating the three options

**Shared prerequisites.** All three options run a model over tickets or knowledge, and tickets contain personal data. Whichever is chosen:

- **Model and external-service review:** legal and security choose and contract the deployment model (external API, cloud-hosted, or on-prem), plus any logging or monitoring service that touches ticket data.
- **Data-handling rules:** external contractors sign an NDA; unmasked tickets stay inside the company environment and enter no external service before that review is complete.

**(A) Fully automatic replies — not recommended now.**

- Some tickets must be decided by people: refunds above NT$30,000 need supervisor approval, and compensation demands or threats involving regulators or the media carry legal and PR implications.
- A wrong reply costs compensation and reputation, far more than the time saved, and correctness cannot be claimed before measuring it.
- *Prerequisite:* data from (B) shows specific categories are accurate enough; open them one at a time after review.

**(B) AI triage and drafts, agents review — recommended.**

- Senior agents say many tickets need two or three systems, and the sample needs are diverse. AI can triage on the three dimensions, extract order numbers and amounts, look up data in advance, draft replies from policy knowledge (RAG), and leave the final check to agents.
- *Risks:* personal data reaching an unreviewed service; misread intent sending drafts in the wrong direction; order-API access review delaying the timeline.
- *Prerequisites:* read access to the order API; discovery of the actual handling process.
- *Design boundary:* AI only reads. Write actions such as refund requests are pre-filled by AI and submitted by agents.

**(C) Knowledge-base Q&A — depends on discovery.**

- Worth building only if looking up knowledge takes a large share of agent time and maintenance is affordable. If so, integrate policy knowledge into (B) for drafting instead of building a separate tool.
- *Risks:* scattered, conflicting documents would make answers cite outdated content; without an owner, accuracy decays over time.
- *Prerequisites:* scope limited to policy knowledge; versions cleaned up and an owner assigned by the support lead; product information read from source systems rather than copied.

### 2.5 What not to solve with AI

- **Knowledge version governance:** which rule is in force is a business decision for the owner. AI only helps convert documents into a searchable format.
- **Approval for refunds above NT$30,000:** a clear business rule. Code checks the threshold and routes to a supervisor; AI does not decide whether approval is needed.
- **Long phone wait times:** TK-1004 and TK-1024 both complain that nobody answers the phone. This is a phone-staffing and systems issue to report to management separately.
- **Visas, passport validity, weather:** set by external authorities and change quickly. Replies cite the official government or airline notice and agents confirm the latest rule.

### 2.6 What not to solve yet

- **Fully automatic replies:** require measured data from (B) to know which categories are safe.
- **Halving headcount:** not a goal at this stage. Until quality is stable, every reply needs agent review, so savings come gradually, starting with shorter handling time.

### 2.7 Rollout order

![Rollout order](figures/rollout_order.png)

Orange marks external prerequisites; blue marks the parallel track.

1. **Discovery:** confirm the process and baseline, and clarify API access, QPS, and the timeline for the model and external-service review. Also assess whether integrating policy knowledge is worth it (curation and maintenance cost vs. agent lookup time). Administrative processes often move slower than development, so raise them early.
2. **Define categories:** derive handling paths from discovery. I propose; the support lead approves and assigns an owner.
3. **Roll out triage in stages:** results are advisory and do not change the existing process. Agents give thumbs up or down, and that feedback becomes labeled evaluation data. Start with priority, risk flags, non-support, spam, insufficient info, non-Chinese, and other-department routing, and link open tickets from the same customer. These do not depend on the handling-path definitions and get urgent and cross-department tickets handled first. Then add handling paths one at a time; collect uncategorized tickets for regular review.
4. **Per handling path, enable lookups before drafting:** open a path only when its system access or knowledge is ready (for example, order paths wait for API access). First show agents the looked-up order and policy data; enable drafting only after lookup accuracy meets the target. Validating lookups and drafting separately makes it possible to locate errors. Each step starts small, is rated by agents, and expands when on target.

System-access requests start in parallel with discovery. If policy knowledge is worth integrating, it is curated in parallel with a named owner. Until the model and external-service review is done, development uses an on-prem open-source model so data never leaves the company; I provide a cost, latency, and quality comparison of deployment options for legal and security to decide.

### 2.8 Response to the support lead's request

The support lead wants automatic replies and half the headcount. The recommendation is to use (B) first to shorten first response time and reduce complaints and negative reviews, keeping those two requests as long-term goals pursued category by category once quality is stable.

## 3. Problem Definition

### 3.1 Goals and non-goals

| Level | Goal |
|---|---|
| **Outcome** | Shorter first response time (measured separately for normal season, peak season, and urgent tickets); fewer complaints and negative reviews caused by slow replies |
| **Intermediate** | Shorter handling time per ticket: agents no longer search across systems, and spend less time writing replies |

**Non-goals** — things each stakeholder might assume are included but are not:

| Stakeholder | Non-goals |
|---|---|
| Support | Fully automatic replies; halving headcount; improving phone support; complaints not caused by slow replies (e.g. tour quality); AI performing write actions; drafting non-Chinese replies; automatic product-information retrieval |
| IT | No changes to the order or ticketing systems, integration only through existing APIs; no request to raise API QPS; no curation of all knowledge documents |
| Legal and security | No training or fine-tuning on customer data |

- **Non-Chinese tickets** are triaged and get looked-up information, but no draft. Chinese drafting comes first, and non-Chinese tickets may be better handled by agents fluent in that language.
- **Product questions** are triaged only and handled manually. There is no product-data API; scraping product pages with source links is a possible later addition.
- **Later extensions:** a separate prompt for non-Chinese lookups and drafting; visa and weather questions answered only from designated official sources with links. Both wait for pilot data on actual volume.

### 3.2 Users and scenarios

**Primary users: front-line agents.**

- Opening a ticket, they see the triage result, looked-up data with sources, suggested actions, and a draft reply.
- They confirm the data and perform any needed action (for example, an order change).
- They review and edit the draft, then send it.
- Their work shifts from "look it up and write it" to "check and correct", and similar tickets can be batched.

**Also affected:** customers (speed and correctness of replies), other departments receiving forwarded tickets (routing accuracy), the support lead (results, risks, failure cases), legal and security (data use and vendor review), IT (system access), and the knowledge owner (ongoing maintenance, if policy knowledge is integrated).

### 3.3 Inputs and outputs

**Inputs:** ticket content and attachments (whether AI should read photos is to be confirmed with support); order data via the order API; policy knowledge (if integrated); open tickets from the same customer (linked to avoid duplicate or conflicting replies).

**Normal outputs:** triage on three dimensions; lookup results with source links; suggested actions; a draft reply (not for non-Chinese tickets).

**Exception outputs:**

- Order not found → tell the agent and use a template asking the customer to confirm order details
- No policy basis found → no draft
- Fits no category → human handling
- Model unavailable → flag the error and retry once; if it still fails, notify the maintainer and route to humans, keeping urgent tickets flagged by rules first in line

### 3.4 Prerequisites

**Blocking — do not start without:**

- Support lead agrees to agent observation and senior-agent time for labeling samples
- External contractors sign an NDA; unmasked tickets used only inside the company environment
- Local hardware that can run an open-source model, for development before the model and external-service review is complete

**Parallel — start now, but they gate later stages:**

- Order-API access request; paths that need order lookups open only after approval
- Model and external-service (logging, monitoring) review; until complete, no pilot with real data, and development uses the local model

### 3.5 Acceptance criteria

**Assumptions** (to be confirmed with historical ticket timestamps and discovery):

- All 8 agents work weekdays and spend about 6 hours a day on tickets; response time is measured in working hours after the start of the shift
- About two thirds of tickets arrive outside working hours and are waiting at the start of the day
- Current handling time is conservatively 8 minutes per ticket
- **Optimistic planning case:** AI assistance saves about 30% of handling time (the best case in public studies, about 5.6 minutes per ticket) on about 83% of tickets, treating only product, external-info, and non-Chinese tickets (about 17% of the sample) as unassisted at 8 minutes. This is an upper bound: the design also keeps complaints, other-department, and high-risk tickets out of drafting, and the PoC marked only half of the support tickets as AI-assisted. The [appendix](#appendix-how-the-targets-were-derived) shows how capacity changes across both assumptions.
- About one in six tickets is urgent (sample ratio)

These handling times will be validated during discovery with a **Wizard of Oz** test: people prepare the outputs the system would produce, mix in erroneous outputs at typical industry error rates, and time agents as they review and correct them.

Targets under the optimistic planning case with current staffing. Outcome targets are re-set once discovery measures the real AI-assisted share and the Wizard of Oz handling times:

| Type | Metric | Target | Data source |
|---|---|---|---|
| Outcome | First response, urgent | Normal season: within 1 working hour; peak: within 2 working hours | Ticket timestamps |
| Outcome | First response, regular | Normal season: within 4 working hours of shift start | Ticket timestamps |
| Outcome | Tickets per agent per hour | About +30% (about 7.5 → 10) | Ticketing-system handling records |
| Quality | Handling-path accuracy | ≥ 90% | Agent thumbs up/down |
| Quality | Lookup and policy-citation accuracy | ≥ 95% | Agent feedback |
| Guardrail | Missed urgent tickets | 0 | Agent reports while handling regular tickets; supervisor spot checks of the non-urgent queue |
| Guardrail | Incorrect content sent | 0 | Supervisor spot checks; customer replies |
| Guardrail | Personal-data incidents | 0 | Security audit |

**Known limits (not acceptance targets):**

- Peak season brings about 700 tickets a day, above the improved capacity of roughly 390–480 depending on assumptions, so regular tickets still back up and cannot all be answered the same day.
- Even in the optimistic case, normal season needs about 6 agents' worth of working time and peak season about 12, so there is no basis to promise a headcount reduction.
- Whether to add staff or widen automation for peak season is a management decision based on pilot data.

### 3.6 Five questions to ask before starting

Each answer determines whether work can start or whether a baseline can be established:

| # | Question | Ask | Risk it rules out |
|---|---|---|---|
| 1 | Can we observe agents and get senior-agent time for labeling? After an NDA, can we develop and test on unmasked tickets inside the company environment? | Support lead, legal | Discovery cannot happen; masking data slows development |
| 2 | How long will review and contracting take for the model and any external service that touches ticket data (logging, monitoring)? | Legal, security | The pilot timeline cannot be estimated |
| 3 | How long is the order-API access review? | IT | Paths needing order lookups stay blocked |
| 4 | Can we export historical tickets with timestamps from the ticketing system? | IT | No baseline to prove improvement or confirm peak-season length |
| 5 | Is there local hardware that can run an open-source model? | IT | No development possible before the deployment review is complete |

## 4. Solution Design

### 4.1 End-to-end workflow

Boxes are actions and diamonds are decisions. Orange is code, purple is AI, blue is human, and grey is a system event. Dashed lines are lookup-failure paths.

![End-to-end workflow](figures/workflow.png)

A ticket enters through the ticketing-system webhook, passes rule checks, and is triaged by AI. Based on the ticket, AI requests lookup tools — `get_order` (order system) and `search_policy` (policy knowledge), possibly both — and code approves them within the ceiling set for the handling path. AI summarizes the findings, suggests actions, and drafts a reply, which goes back to the ticketing system for agent review. Refunds above NT$30,000 require supervisor approval first. Agents perform any needed actions (modify or cancel an order, submit a refund request) in the order system, then send the reply. Tickets handled manually because of a model failure, a lookup failure, or non-Chinese content follow the same back half of the flow. High-risk tickets are handled end to end by a senior agent or supervisor; product, external-info, and non-support tickets involve no refunds and close after handling.

### 4.2 Division of responsibilities

| Role | Responsible for |
|---|---|
| Rules (code) | Linking open tickets from the same customer; non-Chinese detection (share of Chinese characters); personal-data patterns (national ID, phone, bank account, card number); urgent and high-risk keywords; whether the AI-extracted departure date is within 72 hours; whether a refund exceeds NT$30,000. AI can escalate rule flags but never clear them |
| AI | Three-dimensional triage, extracting information from the ticket, requesting lookup tools and performing read-only lookups, summarizing results, suggesting actions, drafting replies |
| RAG / knowledge base | Policy knowledge with sources; no draft when no basis is found |
| Humans | Confirming triage, data, and drafts; performing all write actions in the order system; handling high-risk and non-drafted tickets; supervisor approval for large refunds |

### 4.3 Human-handoff triggers

- **Model service failure:** keep urgent and high-risk flags set by rules and route everything to humans, urgent first
- **Order not found:** tell the agent and use a template to ask the customer to confirm order details; no AI draft
- **No policy basis found:** human handling; no AI draft
- **High risk** (compensation demands, PR or legal mentions): no AI handling or drafting; a senior agent or supervisor handles it end to end
- **Paths without drafting:** product, external info, non-Chinese, other department, complaints and compensation
- **Insufficient info:** first fill gaps from linked open tickets and orders under the sender's account, then re-triage; only if that fails does AI draft a request for missing details
- **Spam:** no human handling; moved to a spam folder with no reply, spot-checked to catch misclassification
- **Refund above NT$30,000:** AI drafts as usual, but after agent review a supervisor must approve before the refund is executed and the reply is sent

### 4.4 Error handling and degradation

- **Service failure:** when the model is unavailable, rule checks keep running, so urgent flags are never interrupted.
- **Quality degradation:** agents can thumbs-down triage, lookups, or drafts during review. If thumbs-downs within an hour exceed a threshold and are clearly above the usual rate, degrade from the failing step onward and hand that step and everything after it to humans. Healthy steps keep running; for example, if order lookups fail, triage and urgent flagging continue.

### 4.5 Personal data and access boundaries

- No real data runs through the model or any external service until legal and security have reviewed it.
- AI is read-only. `get_order` returns only the sender's own orders (by the order number in the email or orders under the sender's account).
- AI requests lookup tools based on the ticket; code approves them against the ceiling for the handling path. Requests above the ceiling are blocked and logged.
- For write actions such as modifying or cancelling orders, AI can only suggest; agents execute.
- Full content (original tickets, order data, drafts) stays in internal systems. External monitoring receives only content-free data such as token usage, latency, and error codes. Access rights and retention for internal logs are decided by security and the support lead.

### 4.6 Logging and trace points

| Step | What to record |
|---|---|
| Intake | Original ticket |
| Rule checks | Rules matched, flags escalated |
| AI triage | Labels on all three dimensions; tools requested and approved (including blocked requests); model and prompt version |
| Lookups | API called, query parameters, data returned |
| Drafting | Draft and cited sources |
| Agent review | Thumbs up/down, corrected triage, thumbs-down reports, content actually sent |
| Supervisor approval | Approver and decision |

## 5. Metrics and Launch Gates

### 5.1 Monitoring metrics

Tracked continuously during the pilot; targets carry over from the acceptance criteria.

| Metric | Numerator ÷ denominator | Data source | Target |
|---|---|---|---|
| **Task success rate** | Tickets with a first response within the target time ÷ tickets entering the support flow | Ticket timestamps | Urgent: within 1 working hour (normal) or 2 (peak); regular: within 4 working hours of shift start (normal) |
| **Human takeover rate** | Tickets on AI-assisted paths that ended up handled by a person ÷ tickets routed to AI-assisted paths. Reported by reason: lookup failure, degradation, no policy basis (no draft produced), agent thumbs-down, or more than half the draft's characters rewritten | System logs, thumbs-down records, draft vs. sent comparison | No target; watch the trend per reason. The rewrite threshold is calibrated during the pilot |
| **Error rate** | Handling-path error rate: tickets whose handling path agents corrected ÷ tickets that went through handling-path triage (including urgent; excluding high-risk, other-department, spam, non-Chinese, which are tracked by the guardrail metrics below). Also reported per path<br>Lookups and citations: tickets where agents reported a data or citation error ÷ tickets with AI lookups | Agent corrections and reports | Handling path ≤ 10%; lookups and citations ≤ 5% |
| **Handling time** | From an agent opening an AI-assisted ticket to sending the reply; large refunds needing approval tracked separately | Ticket timestamps | About +30% tickets per agent per hour |

### 5.2 Guardrail metrics

| Metric | Target | What it protects against | Data source |
|---|---|---|---|
| Missed urgent tickets | 0 | Urgent tickets queued as regular, e.g. nobody handles a customer departing tomorrow | Agent reports while handling regular tickets; supervisor spot checks of the non-urgent queue |
| Incorrect content sent | 0 | AI gets an amount or policy wrong and the agent does not catch it | Supervisor spot checks; customer replies |
| Personal-data incidents | 0 | Customer data sent to an unreviewed external service or included in a reply to another customer | Security audit |
| Support tickets misclassified as spam or forwarded to the wrong department | 0 | A ticket that needs a reply is archived or handed to another team and the customer never hears back | Every archived or forwarded ticket confirmed by a person |

A target of 0 is a gate over an observation window, not a guarantee of zero risk, so each result is reported with the number of tickets observed. By the rule of three, zero incidents in *n* tickets supports a rate below about 3/*n* at 95% confidence: 0 in 300 tickets means below about 1%.

### 5.3 Promotion and rollback criteria

Rollback means turning off the failing feature and handing it back to humans.

| Stage | What runs | Promote when | Roll back when |
|---|---|---|---|
| **PoC** | The model and deployment planned for production, tested offline on historical tickets labeled during discovery (hundreds, covering normal and peak season with enough urgent tickets) | Handling-path error ≤ 10%; zero missed urgent tickets, zero spam misclassifications, zero wrong-department forwards; Wizard of Oz shows about 30% handling-time savings | Still below target after tuning → narrow the scope, e.g. ship triage only |
| **Pilot** | Real tickets and agents, opened in the rollout order: triage → lookups (after order-API approval) → drafting. Each step must meet its error target for 2 consecutive weeks before the next opens | After everything is open, 2 consecutive weeks on target for task success, handling time, and error rate, with every guardrail at 0 | See below |
| **Production** | All tickets | — | Same as pilot |

**Rollback during pilot and production**, by where the problem occurs:

- **Missed urgent ticket, spam misclassification, or wrong-department forward:** that triage category goes back to advisory-only, agents check every ticket as before, and it reopens after the fix.
- **Incorrect content sent**, handled by severity:
  - **Severe** (a wrong amount, a refund or compensation commitment, or policy or legal terms that bind the company): stop drafting on that path immediately.
  - **Other errors:** after 1 incident, find the root cause, raise spot-check rates for that path, and highlight error-prone fields in drafts (amounts, dates, policy clauses). If incidents involve **two different agents within 2 weeks**, stop drafting on that path: errors getting past more than one reviewer point to the system or the review design rather than one person's lapse. Repeated incidents from the same agent are investigated the same way, since they can also come from the interface or the review design.
- **Personal-data incident:** the only case that pauses everything; all work goes back to humans.
- **Human takeover rate rising for 2 consecutive weeks:** step back one stage and investigate.

## 6. PoC: Ticket Triage

The PoC covers triage because it is the first rollout stage and the only one that does not depend on order-API access or curated policy knowledge. It implements the triage half of the workflow on the 48 sample tickets, using a local `qwen3:8b` model via Ollama plus deterministic rules. Run instructions, data issues, design trade-offs, and the top three steps toward production are in [`poc/README.md`](../poc/README.md); results for all 48 tickets are in [`poc/output/triage_result.csv`](../poc/output/triage_result.csv).

### 6.1 Scope

- **Does:** classify the handling path, flag urgency, high risk, and personal data, extract departure date and claimed amount, merge model and rule results, and decide route, allowed tools, and next step for each ticket.
- **Does not:** call the order API or policy retrieval (tools are stubs), generate drafts, integrate with a ticketing system, or send anything.

### 6.2 Results

| Outcome | Tickets |
|---|---|
| Suggested for archiving (spam, test data) | 2 |
| AI-assisted paths: agent reviews a future AI draft before sending | 22 |
| AI-assisted path that also needs supervisor approval | 1 |
| Human-only: agent handles | 12 |
| Human-only: forward to another department | 8 |
| High risk: senior agent or supervisor handles | 3 |

Half of the 46 support tickets landed on human-only paths, far more than the 17% assumed in the optimistic planning case; the [capacity table](#appendix-how-the-targets-were-derived) shows what that does to the estimate. The model requested 11 tools on 8 tickets that the per-path ceiling filtered out, all on human-only paths.

There is no accuracy figure: there is no labeled evaluation set yet, and the category definitions were written after reading these 48 tickets, so results are optimistic. Even 48 correct out of 48 would only support an error rate below about 6% by the rule of three.

### 6.3 Representative cases

**Layered guardrails (TK-1029).** A customer demands NT$45,000 in compensation after the tour leader failed to show up and the family missed their flight. The model flagged it urgent and high-risk, a rule matched the word "compensation", and code flagged supervisor approval because the claimed amount exceeds NT$30,000. The ticket went to a senior agent with no AI draft, and the model's requests for `get_order` and `search_policy` were filtered out by the high-risk ceiling.

**Wording hides the real request (TK-1004).** The customer complains that the phone line went unanswered for 40 minutes, but only wants to know when the itinerary will arrive. The model classified it as a complaint, a human-only path, when the real need is an order lookup. The fix is labeled examples from discovery, not more rules.

**Urgency flagged too broadly (TK-1002).** A customer wants to cancel a tour departing in about ten days because a parent was hospitalized. The model marked it urgent from the emotional context, although the departure-date rule did not fire. Of 12 urgent tickets, 5 were flagged by the model alone, and 4 of those did not need same-day handling. Urgency needs calibration on the evaluation set.

## 7. Hypothetical Pilot Incident Review

*This is a scenario exercise, not a pilot that was run.*

**Scenario.** Four weeks into the pilot, 45% of tickets are handled with AI assistance and first response time has dropped from 6 hours to 1.5 hours. But three AI drafts with errors were sent without agents catching them, causing complaints. Agents have stopped trusting the system and route almost everything to manual handling, so the takeover rate is climbing.

**Recommendation to decision-makers: adjust, do not pause.** The faster first response is a strong positive signal, but three incorrect replies and falling agent trust are real costs, so the overall value is not yet settled. Keep the parts confirmed to work, and stop or restrict the affected ones instead of withdrawing the whole system. Follow-up with affected customers is handled by support under existing policy.

**Three immediate actions:**

1. **Contain.** Apply the rollback criteria in §5.3: a severe error stops drafting on that path at once; otherwise check the two-agent rule, and either stop drafting on the path or raise its spot-check rate. Other paths keep running. Tell agents which path is back to manual and that they will not see suggestions there until it is fixed and relaunched.
2. **Trace each incident end to end.** For each of the three, check the source data, the lookup, the generated draft, how the draft was presented, and the review step, then fix what the trace shows. The path's error rate against its target decides whether the path stays open, not where the fault lies: an on-target aggregate can still hide a concentrated failure on one path, amount range, or policy, and an interface can make errors hard to spot.
3. **Rebuild trust with agents.** Share what the trace found and what changed. Where review was part of the cause, train agents on historical tickets that mix correct and incorrect drafts. On relaunch, mark the steps and fields that failed before so agents know where to look closely.

## Appendix: How the targets were derived

**Handling-time estimate**

- The closest studies of asynchronous text replies are healthcare systems using AI to draft replies to patient messages for human review: Stanford found no significant change in handling time ([Garcia et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10955355/)); UC San Diego found reading time increased by about 22% ([Tai-Seale et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11019394/)); NYU observed about −7% turnaround on replies that used a draft ([Mandal et al., 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12491571/), observational).
- Live-chat support: +14% resolutions per hour ([Brynjolfsson et al., NBER](https://www.nber.org/papers/w31161), 5,179 agents) and −8.5% average handling time ([arXiv version](https://arxiv.org/abs/2304.11771)). LinkedIn's support team reported −28.6% median resolution time after adding knowledge-graph RAG ([Xu et al., SIGIR 2024](https://arxiv.org/abs/2404.17723)); this measures wall-clock resolution, not handling time.
- Savings are limited because reading and judgment remain human, checking AI output adds reading time, and actual usage is only about 20–40% (draft usage of about 20% at Stanford and NYU; 38% adherence in Brynjolfsson et al.). Across these studies, typical savings are about 5–15% and best-case about 15–30%. None of them is a travel or email-ticket setting, so the range is a planning input to be replaced by the Wizard of Oz measurement.

**Capacity across assumptions**

Eight agents × 6 hours = 2,880 working minutes a day, or about 360 tickets at today's 8 minutes. Capacity with AI assistance depends on the share of tickets that get it and on how much time it saves on them:

| Share of tickets AI-assisted | 15% faster | 30% faster |
|---|---|---|
| 50% (close to the PoC's routing) | About 390/day | About 425/day |
| 83% (optimistic planning case) | About 410/day | About 480/day |

Every combination stays far below the roughly 700 tickets a day of peak season. The first-response estimates below use the optimistic case (about 6 minutes per ticket, 480 a day), so they are a best case.

**First response**

How long it takes after the shift starts to clear the overnight backlog. Urgent tickets go first, but they are part of the backlog, so reordering does not change the total time to clear it:

| | Normal (350/day) | Peak (700/day) |
|---|---|---|
| Overnight backlog | About 233 | About 467 |
| Time to clear the backlog | About 3.9 working hours | About 7.8 working hours |
| Of which urgent | About 39, about 36 minutes | About 78, about 1.2 hours |
| Daily capacity vs. intake | About 130 spare | About 220 short |

The urgent targets (1 hour normal, 2 hours peak) and the 4-hour regular target leave buffer above these estimates. At a shortfall of about 220 tickets a day, a peak lasting 1 week, 2 weeks, or 1 month (working days) means the last tickets wait about 2.3, 4.6, or 10 extra working days.

**Quality thresholds** (based on public studies, not measured in this scenario)

- **Handling-path accuracy ≥ 90%:** intent classification over 289 classes for Chinese e-commerce after-sales support reached 93% ([JDDC, LREC 2020](https://arxiv.org/abs/1911.09969), non-LLM). Anthropic's [ticket-routing guide](https://platform.claude.com/docs/en/about-claude/use-case-guides/ticket-routing) targets 90–95% (vendor documentation without a cited measurement). This scenario has far fewer categories, but results on real tickets are much lower without task-specific data: 0.34–0.57 for zero-shot GPT-4 on Italian IT tickets ([Arici et al., 2023](https://ceur-ws.org/Vol-3551/paper4.pdf)) and 60–76% for a multilingual classifier on Zendesk tickets ([arXiv 2309.08647](https://arxiv.org/abs/2309.08647)). Labeled examples from discovery are therefore needed as few-shot examples or training data, validated on this scenario's own labeled set.
- **Lookup and citation accuracy ≥ 95%:** grounded answer generation in LinkedIn's support system shows about a 5% hallucination rate ([arXiv 2608.10224](https://arxiv.org/abs/2608.10224), LLM-graded); this design also refuses to draft without a policy basis. Commercial legal RAG tools hallucinated in 17–33% of queries ([Magesh et al.](https://arxiv.org/abs/2405.20362)), so the risk should not be underestimated.
- The Wizard of Oz test mixes in errors at these rates (about 10% misrouted, 5% wrong citations) to verify agents can still finish within the target handling time.
