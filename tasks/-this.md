
Seen

- backlog
- idea -> now idea_2
- trnscript


Orginal idea from vid
----------------------------------------------------------

- The closed-loop self-improving system (the engine) — capture → analyze → propose → improve, artifact-rich, gets better over time
- A whole-company model — loops everywhere, queryable org, software factories, token-maxing, new org archetypes, no middle management

Details

- Closed loop vs open loop — monitor output, adjust to a stated goal. ✅ (loop steps 1–6)
- Every action → an artifact the AI learns from — the append-only store is "make it queryable / legible to AI." ✅
- Self-improves over time — next run ingests accumulated history. ✅
- Propose accurate plans — and v1's example domain is literally the video's: engineering sprint planning. ✅
- Humans at the edge — human at the gate, agent does the work. ✅


Orginal idea vs v1
----------------------------------------------------------

| Transcript (timestamp) | In v1? |
| :--- | :--- |
| Closed loop: "captures information, feeds it back… improves over time," "monitors output and adjusts to meet the stated goal" (1:41–2:19) | ✅ Core of v1 — loop steps 1–6; goal+metric as data, measured metric recorded, history fed back |
| "Every important action should produce an artifact the intelligence can learn from and self-improve" (2:36–2:42) | ✅ append-only artifact store; next run ingests it |
| "Status, decisions, and outcomes continuously captured and fed back" (4:27–4:31) | ✅ exactly the input/decision/outcome records |
| Concrete example: engineering sprint planning → analyze what shipped vs. needs → propose accurate sprint plans (3:00–3:42) | ✅ named as v1's example domain |
| "Provide models with as much context as an employee" (4:13–4:15) | ⚠️ v1 bounds context (token reality); relevant-slice retrieval only half-done → bounded-retrieval.md |
| The sprint example's sources: Linear + all Slack channels + customer feedback/Pylon/GitHub + Notion/Google docs + sales calls + standup recordings (3:06–3:19) | ⚠️ v1 = one connector. Even the video's flagship example is multi-source; v1's instance is thinner |
| AI notetaker, minimize DMs/emails, agents in all channels (2:45–2:51) | ❌ deferred → multi-channel-capture.md |
| Dashboards across everything — revenue/sales/eng/hiring/ops (2:54–2:58) | ❌ deferred → dashboards.md |
| Software factories: spec+tests → agents write code, iterate to threshold (4:42–5:47) | ❌ deferred → software-factory.md |
| "AI = the operating system the company runs on," loops everywhere (1:17–1:39) | ⚠️ now blank core + pluggable domain pack — one domain per deploy (domain-pack packaging done); many loops in one app still out of scope |
| Org model: humans at edge, no middle management, IC/DRI/AI-founder, token-maxing, high API bill (6:08–8:53) | ➖ out of scope — company philosophy, not a system to build |

Provide models with as much context as an employee: basically means LLM gets all context a company has
in reality (token usage): smarter retrieval (feed the most relevant context, the realistic version of "as much as an employee")


Next
----------------------------------------------------------

- tool-registry

- [text](backlog/website-domain-pack.md) — captured: `web-source` connector (search|pages), config-sourced goal, actions create_page (reversible, auto-runnable) / edit_content / change_layout / remove_page (all reversible=false → held); site under `data/site/` versioned via the new git integration. Effort L (phased).

  - See questions in task
  - Woud you change something?
  - Check for errors

- [x] Make nice CLI [text](backlog/run-triggers/interactive-cli.md) — DONE (S): interactive REPL (`python -m night_forge_mini` / `shell`); run/inbox/approve/reject/trace, approve by inbox #. M (edit-before-approve + streaming) remains.

- [ ] Check backlog, what should we add? (see also above)
  
  by effort in parens
  
  1. [x] bounded-retrieval — DONE (S): KB context now a bounded keyword slice (kb_context_max, default 20). M (embeddings) remains in backlog.
  2. [x] stale-edit-guard — DONE (S): edit_entry stamps a body fingerprint at propose; approval refuses (error outcome) if the body changed since. No lost-update.
  3. observability (S) — wire one tracer (Langfuse/LangSmith) through the existing LLM wrapper; store is already trace-shaped.
  4. cost logging (S, roi-measurement) — per-run token/$ visibility; full ROI attribution comes later (L).
  5. approval-ui (S read-only) — web inbox over the log; lowers the cost of keeping a human at the gate.
  6. run-triggers/ (S→M) — alternative invocation methods (most important first). Unattended ones need a pending-notification (pairs with approval-ui):
     - [x] interactive-cli (S) — DONE: REPL console (`python -m night_forge_mini` / `shell`); approve by inbox #.
     - scheduler-daemon (S) — interval poll loop; the realistic "endless loop" for unattended operation.
     - filesystem-watch (S) — fire a run when a new artifact lands (event-driven; fits the KB folder).
     - http-api-server (M) — HTTP endpoints over the engine; substrate for web UI, remote, webhooks.
     - webhook-trigger (M) — external event POSTs in to fire a run (builds on http-api-server).
     - library-embed (XS) — call the engine in-process; already works, just document/harden.
  7. data-governance (S first step) — scoped read-only creds per connector; do when a 2nd connector lands.
  8. autonomous-actions (M) — earned autonomy (risk classifier + rollback) once hand-curating the allow-list hurts.
  9. drift-detection (L) — needs accumulated metric history first.
  10. multi-channel-capture (L) — many integrations + consent.
  11. dashboards (L) — only pays off with multiple domains.
  12. software-factory (XL) — separate, huge specialization.

  - maybe git-library instead of CLI

- [ ] Self improving homepage
  - Simple web design => expands to better
  - Layout, site elements and content improves
  - Must have content improves
  - Constraints: e.g. logos, colors, ... for CI


Advanced
----------------------------------------------------------

- Wahlweise Aktionen als file only, check at end, then run later
- Anything weak in /backlog? Needs improvement?
- [ ] Add stuff like [text](backlog/domain-pack-template.md)


Done
----------------------------------------------------------

### 2026-06-26

- [x] Add a second domain pack "website". It starts with a minimal dummy website, then it consumes content from the internet either using web search or a specified list of pages. The LLM uses that content to improve the website. It may:

  - Edit content
  - but also change layout and design
  - create or remove new sub pages

  The exact goal for the LLM and how to improve the website is given by the user in config.

- [x] Git integration to version the materialized artifacts (needed for the website pack) [text](backlog/git-integration.md) — no git integration today; history lives only in the append-only JSONL log, materialized files keep latest version only.

- [x]

  - The whole thing e.g. the whole site is committed/pushed after each successful loop. Do I see this right?
    - but we could use a config setting: per action, per run, ...
  - Typically we push to github, only if easy: we can use open a local git as a fallback if git is on and github missing
  - git in configuration as an optional entry
    - put in core config or domain pack specific?
  - existing project `.git/` is the sources repo, an installation would use its own repo somewhere in a different folder or if possible for testing here in a subfolder (like /try)

### 2026-06-21

- [x] The intention wasn't to have multiple domain packages in one app as you said earlier. Instead we want a reusable blank system that has no use case, then we plug excatly one domain pack in and deploy it like this.

  I think we should skip the BUILD.md idea and make a system that has all reuasble parts and one demo domain pack.

  Read domain-pack-template.md again. Can we use the /skb implementtion as a basis?

  Outcome: /blank implementation and /domains/kb seperately. Then I could just merge these 2 in a new folder to get the running system.

  One thing I modified: config.json and /data originally were in the project base folder of the project, I moved them to /skb but I am unsure what the right location is for python and a multi domain system. Same for .env, requirements.txt and the readme.

- [x] Does /skb implement all from idea_2.md now?

- [x] I want to be able to make multiple different systems with idea_2.md.

  Variant 1: see tasks/backlog/domain-pack-template.md

  Variant 2: We extract the inintal project idea "knowledge base" from idea_2.md and put it in a BUILD.md so that idea_2.md is resusable and we could write multiple BUILD.md files. One BUILD-?.md plus idea_2.md is used to implement a specialized system.

  Or something different. Wnat would you recommend?

- [-] Maybe move config.json and /data out again (if it is like this in python)
- [x] Maybe verify we have all from idea_2

### 2026-06-15

- [x] Compare idea_2 against trnscript.txt which is a youtube video transcript and the original app idea from Y Combinator. Is v1 still the system descriped in the video?
- [x] ASCII ?
- [x] Programming lang ?
- [x] Make v1

  Looks like we have a ticket use case hard coded in v1 and use Anthropic API calls.

  - We use OpenRouter and gemini 3 flash preview API calls as well as Gemini and Ollama (Modular). OpenRouter currently is default.
  - For artifacts use JSONL.
  - I'd like to have a differnet less code related use case for v1. Suggestions?

- [x] basic agent only, defer all non basic featuers for simplicity

  idea_2 is the dev-prompt or "app concept" in that case

  Please apply your suggestions and move defered featurs to tasks/backlog (one file per task) or merge with existing (if any)

  Make sure that v1 still is kind of "modular" so that we easily can upgrade it later

- [x] How would artifact store work ?
- Defer some Must-do guardrails ?
  - [x] How would approval gate work?
  - [x] No cost logging in v1 defer it
- We keep logging simple for now, just append and forge
  - [x] what type of log? hierarchical?

- [x] Minimal guardrails for v1
- [x] "agent suggests; it doesn't act on the outside world unentitled"
  - Is the system currently runable autonomously at all or does any action require human feedback?
  - The agent should be possible to make stuff on its own and do certain (scoped) actions
  - some actions may required human approval first

- [x] Verify /backlog against idea_2. Is idea_2 made in a way so that the backlog features are "plug and play" or should we add something to idea_2 so that add features is easier later?

- [x] More errors or gaps in v1 that we need to fix?
- [x] Artifactas and approval seems to be log entries only

### 2026-06-11

Is the system made in a modular way so that we could specialize it just by adding "modules" e.g. connectore?

 --

Make a new file idea_2.md. Add those of your suggestions that we must do in v1. Write optional features to tasks/backlog one file per feature.                                                                                                                                    
When there are features that is too big for v1 (large effort) we defer it to a later version but prepare v1 to be able to add it later as easy as possible. We want a v1 that is small enought to implement it now, but it should be a working system.    

 --

What do you think about that system? Is that good or is there something that you would improve?

 --

In trnscript.txt is a trnscript of a youtube video. Please extract the app idea of the self improving system to a new file idea.md. Make a generally usable system that could be specialized to multiple things. Keep idea.md as short as possible e.g. use short outlining, but include all mentioned features.
