# Self-Improving Closed-Loop System

> A generic intelligence layer that any process runs *through*. It captures every
> action as an artifact, feeds outcomes back into an AI core, and continuously
> improves the process. Specialize it to any domain (engineering, sales, ops, HR…).
> Source: YC talk by Diana — youtube.com/watch?v=EN7frwQIbKc

## Core Concept
- **Closed loop, not open loop**: every process is self-regulating — monitor output, adjust process to meet a stated goal.
- **Intelligence at the center**: workflows, decisions, and processes flow through one constantly-learning AI layer (the "operating system"), not a tool bolted onto existing flows.
- **Humans at the edge**: people guide/judge; AI does the routing and execution. Minimal human middleware.

## The Loop (engine)
1. **Capture** — every important action produces an artifact.
2. **Ingest** — feed artifacts into the intelligence layer (full context, like you'd give an employee).
3. **Analyze** — assess what happened vs. the goal (what worked, what didn't).
4. **Propose** — generate next actions / plans, more predictable & accurate.
5. **Improve** — iterate until a probabilistic satisfaction threshold is met.

## Make Everything Queryable (legible to AI)
- Record meetings (AI notetaker).
- Minimize ephemeral DMs/emails; embed agents in all communication channels.
- Custom dashboards aggregating *all* domain data.
- Goal: org/process is queryable, artifact-rich, and up-to-date by default.

## Generic Components
- **Connectors**: pull from any source (tickets, chat, email/feedback tools, code repos, docs, call/standup recordings).
- **Artifact store**: durable record of every action/decision/outcome.
- **Agent core**: analyzes, plans, and self-improves over time.
- **Dashboards**: unified real-time view across all inputs.
- **Notetaker / capture agents**: embedded in meetings and channels.

## Software-Factory Mode (build specialization, evolution of TDD)
- Humans write a **spec** + **tests/scenario validations** defining success.
- Agents generate implementation and iterate until tests pass / threshold met.
- Human defines *what* to build and judges output; agent owns the code.
- End state: repo holds only specs + test harnesses, no handwritten code.
- Effect: surround one builder with a system of agents → 1,000–10,000x output.

## Operating Principles
- Give models as much context as a human employee would get.
- Maximize **token usage, not headcount**; accept a high API bill vs. inflated team.
- Remove every layer of human routing — velocity = information flow.
- Three human archetypes: **IC/builder-operator** (everyone builds, brings prototypes not decks), **DRI** (one person, one outcome, owns result), **AI-founder** (builds, coaches, leads by example).

## Specialization Examples
- **Engineering / sprint planning**: ingest tickets + eng chat + customer feedback + roadmap docs + call/standup recordings → analyze what shipped vs. customer needs → propose accurate sprint plans. (Reported: ~half sprint time, ~10x output.)
- Also: sales, ops, hiring, support, finance — same loop, different connectors and goal.
