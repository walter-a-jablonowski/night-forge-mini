
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

- /blank: basic system
- /domains: modular domain packs for use cases
The blank system plus pne domain pack is merged in a new folder to get a running system.

- [x] Add Claude Code as AI — explored 2026-09-10, task written:

  - [text](backlog/claude-code-backend-refinements.md)
  - [text](backlog/analyze-context-amplification.md)
  
  [text](v%20done/260911%20-%20claude-code-backend.md). NOT a 4th `providers{}` entry — the CLI is an
  agent that runs the tool loop itself, so it needs a backend SEAM plus an MCP bridge over
  `tools/registry.py`. Refs: grid-view `lib/ai/claude.php` + `mcp/grid_mcp.php`,
  dev-commander `lib/agents/base.py`. Covers the provider/agent clean-up too — the
  `model.fake` branches in every pack are the current smell.
  - [x] BUILT 2026-09-11 — backend seam (`backends/`: base/http/fake/claude_code) + the
    stdio MCP bridge (`mcp_server.py`). A full analyze pass ran on the subscription
    (run-246291a8): 5 actions, all auto-ran, site left at 5 pages / 0 broken links.
    145 tests. Set `"backend": "claudeCode"` in config; one-shot calls (judge metrics)
    still go to the configured provider.
  - [ ] [text](backlog/claude-code-backend-refinements.md) — edges left on purpose:
    per-tool span timestamps, the one-shot/HTTP combination, measuring a turn's cost
  - [x] both open questions decided 2026-09-10 (per-ROLE backend: analyze=Claude Code,
    judge=cheap http; fresh CLI session per run — the cross-run cacheable prefix is only
    ~856 tokens, and within-run caching is the CLI's own)
  - [ ] [text](backlog/analyze-context-amplification.md) — one pass resends its context
    4-6x (measured: 28.7k chars of content sent as 166k); found while costing the above

- [ ] First page that the model could simple healthy nutrition
  - Ingredients
  - Simple meals
    - fast to make (sample: put in a boal, heat up, ready)
    - good combinations of ingredients (nutrients) per meal
    - cheap (only if possible, price is lower priority)

- [x] tool-registry.md done ?
- [ ] Verify

  What is missing before a daemon would be safe

  - which? No goal-reached termination. The metric is measured and logged, but never compared against a target — nothing says "score ≥ X, stop".
  - which? No convergence detection. N consecutive runs with no metric improvement does not halt anything.
  - kb doaian: search mode breaks quiescence. Website connector phase 3 (connector.py:12) makes input effectively infinite — the watermark stops protecting you, and then only the gate does.

- [ ] Does this app have any mechanism that will block progress for certain actions until a human appoves or do we rely on git / logs only ?
  - allow lists in code (see also diagram)
  - see also backlog below

- [x] Make nice CLI [text](v%20done/260621%20-%20interactive-cli.md) — DONE (S): interactive REPL (`python -m night_forge_mini` / `shell`); run/inbox/approve/reject/trace, approve by inbox #. M (edit-before-approve + streaming) remains.
  - [ ] try


### Backlog
  
- 0.2.0/0.2.1 — Fable 5 review — DONE (0.2.1 = REPL robustness + LLM timeout/retries)
- 0.3.0 — website domain pack
- 0.4.0 — first second-writer feature (scheduler-daemon or approval-ui) together with sqlite-store, so the storage is designed around its first real consumer
  [text](backlog/sqlite-store.md)
- 1.0.0 — core-as-package, because pip-installing the core is the moment the Pack seam becomes a frozen public API — the honest definition of 1.0 for this project  
  [text](backlog/core-as-package.md)

by priority, effort in parens (reordered 2026-07-06 after the review changes)

1. website-domain-pack (L, = 0.3.0) — phases 1+2 DONE (2026-07-28); only phase 3 (connector `search` mode) is left, and it is build-only-if-needed. [text](v%20done/260728%20-%20website-domain-pack.md)
2. observability (S) — wire one tracer (Langfuse/LangSmith) through the existing LLM wrapper; store is already trace-shaped. MORE urgent since agentic analyze: several model calls per run, and tool_call spans map 1:1 to tracer spans.
3. cost logging (S, roi-measurement) — per-run token/$ visibility; same reason as observability (run_tools multiplies calls). impact_report now supplies the value side for the later ROI join (L).
4. data-governance (S first step) — scoped read-only creds per connector. Trigger fires WITH 0.3.0: web-source is the 2nd connector (+ search API key).
5. approval-ui (S read-only) — web inbox over the log; lowers the cost of keeping a human at the gate. Matters more for the website pack (diffs for overwrite/delete).
6. run-triggers/ (S→M) — alternative invocation methods (most important first). Unattended ones need a pending-notification (pairs with approval-ui). First one that lands pulls sqlite-store into the same release (0.4.0):
    - scheduler-daemon (S) — interval poll loop; the realistic "endless loop" for unattended action.
    - filesystem-watch (S) — fire a run when a new artifact lands (event-driven; fits the KB folder).
    - http-api-server (M) — HTTP endpoints over the engine; substrate for web UI, remote, webhooks.
    - webhook-trigger (M) — external event POSTs in to fire a run (builds on http-api-server).
    - library-embed (XS) — call the engine in-process; already works, just document/harden.
7. agentic-analyze remainder (M) — token budget for the tool loop + quality eval across runs (core+kb part DONE 2026-07-05, see tasks/v done; website adoption happens in 0.3.0).
8. autonomous-actions (M) — earned autonomy (risk classifier + rollback) once hand-curating the allow-list hurts. 0.3.0 ships its first concrete instance (git-backed autonomy); the general version stays deferred.
9. drift-detection (L) — substrate now exists (impact_report = predicted-vs-actual per run); still needs accumulated history before the statistics mean anything.
10. multi-channel-capture (L) — many integrations + consent.
11. dashboards (L) — only pays off with multiple domains.
12. software-factory (XL) — separate, huge specialization.

done: bounded-retrieval (S; embeddings-M now likely unnecessary — agentic reads supersede it) · stale-edit-guard (S) · interactive-cli (S) · tool-registry (S, incl. model function-calling)

- maybe git-library instead of CLI


Advanced
----------------------------------------------------------

- Wahlweise Aktionen als file only, check at end, then run later
- Anything weak in /backlog? Needs improvement?
- [ ] Add stuff like [text](v%20done/260621%20-%20domain-pack-template.md)


Done
----------------------------------------------------------

### 2026-09-05

- [x] I guess this currently is a endless running system right? Does it already have any stop mechanism?

- [x] [text](v%20done/260728%20-%20website-domain-pack.md) — phases 1+2 DONE 2026-07-28. Actions: create_page / add_asset (reversible, auto-run) + edit_content / change_design / remove_page (reversible=false → auto-run only while git is healthy, else held). `change_layout` dropped as redundant with edit_content. New core tool `image_search` (Openverse, keyless). Hard constraints + asset licensing ladder enforced inside the actions. Phase 3 (`search` mode) deferred, build-only-if-needed.

  - [x] See questions in task
  - [x] Check for errors
    - try/website/ is a ready merged deploy, needs OPENROUTER_API_KEY
    - see also
      - [x] tasks\backlog\website-domain-pack.md
  - [x] Real-model run in try/website/ — DONE 2026-09-04 (run-7eb9729b), redeployed clean.
    `z-ai/glm-5.2:free` unusable (only provider 429s); used `dots-studio/dots-3-note-preview:free`.
    Exposed 3 defects, one file each:
    - [x] [text](v%20done/260904%20-%20run-on-internal-state.md) — no run when only the site has pending work — FIXED (Pack.pending_work + anti-spin guard)
    - [x] [text](v%20done/260904%20-%20llm-json-retry.md) — one malformed JSON reply killed a whole run — FIXED (bounded retry with the parse error fed back)
    - [x] re-run try/website live — DONE 2026-09-05. run-a257a9c6 fired with `captured: 0`
      (pending-work path, no new input), 5/5 actions ran, snacks.html created, site now
      4 pages / 0 broken links / 4 SEO. Two new findings, one file each:
    - [-] [text](v%20done/260905%20-%20website-action-precondition-confusion.md) — wrong action for the target state
      (3/5 refused in run-393b4eee); NO FIX NEEDED — the failure feedback self-corrected it next run
    - [x] [text](v%20done/260905%20-%20json-parse-failures-must-be-retryable.md) — a 64714-digit number crashed the
      judge metric because ValueError != JSONDecodeError — FIXED
    - [x] [text](v%20done/260905%20-%20write-actions-accept-wrong-file-shape.md) — a full HTML page
      was written into style.css; no guard noticed — FIXED (shape floor: content must match the
      file kind). Leftover idea split out: [text](backlog/styles-ok-metric.md)
    - all resolved files archived to tasks/v done/ (260904/260905). Leftovers kept as new
      backlog items: [text](backlog/styles-ok-metric.md), [text](backlog/salvage-partial-model-json.md),
      [text](backlog/run-when-metric-below-target.md), [text](backlog/metric-display-rounding.md)
    - [x] [text](v%20done/260904%20-%20website-analyze-prompt-tools.md) — model calls actions as tools — FIXED, rerun run-9d177565 clean
    - [-] ~~failed analyze eats the input~~ — WRONG, no such bug: `seen_snippet_ids` already
      counts only runs that reached `analysis`, so a crashed run's snippets are re-offered
      (verified; covered by blank/tests/test_store.py). Backlog file deleted.
    - [x] [text](v%20done/260904%20-%20hard-constraints-bypassable-by-action-choice.md) — edit_content on .css skipped the color check — FIXED (check follows the file, not the action)

### 2026-07-11

- [x] Open questions website-domain-pack.md:

  - Site shape: No frameworks at all for now. Typically plain html/js/styles. Some sites might use PHP but custom development
  - Design changes safely: This one is unclea, don't we have git to see the diff or set back changes?
  - Content-change re-fetch: This is resolved no, right? see comment in file
  - Goal/metric: LLM-as-judge makes sense, metric as well. Configurable in site config what should be used. A metric could also be a piece of code
  that queries something or runs a tool e.g. some SEO relevant value of whatever. So, we merge the main app (blank) with the website domain pack,
  then we could still extend this installation by providing custom metric implementation. The web domain pack could also include some ready to use
  metric modules that generally make sense.

### 2026-07-06

- [x] Below is roughly what the website domain pack does. Verify it can do this.

  This list isn't neccessarily complete and can be improved or changed:

  - Starts with a simle dummy page => expands to better
  - The user defines the goal(s) for the improvements e.g. in a prompt (via config switch where that makes sense)
  - Does web searches, fills content, adds images
  - Also improves site layout, adds componentes
  - Also improves the styles
  - Improves SEO
  - User may also define constraints: e.g. use avoid certain colors, or use a specific logo

- [x] tool-registry
  - [x] fetch_url tool isn't enough for website domain, we need search and fetch
    - Tavily Exa

- [x] I also like using Jina Reader. I currently use the free version and just prepend r.jina.ai/ in front of an URL. Paid version (if present) would be optional.

- [x] We make a review for this system. It is an extensible system where an AI constantly improves an artifact.

  - /blank: main app
  - /domains: for specific use cases
  - Installation: One domain merged with one domain pack on disk
  - /tasks/-this.md: my current task file
    - currently developing tools and website domain pack (stopped for reviewing the main app) 
  - /tasks/backog: the backlog

  Review this system. Is it good as it is or would you improve something? No details or trivial improvements, focus on the main parts. Focus in /blank, the domain packs are less important and still in development.

- [x] Beside the gaps we fixed how do you like this system in principle? Is the basic app principle what you would implement if you had to start a similar system from scratch or would you do a different system or would you change only parts of it?

- tasks/review
  
  - [x] `structured-output.md`   | S      | anytime — do first, de-risks the next one                                                           |
  - [x] `agentic-analyze.md`     | M→L    | the one real architectural evolution; after structured-output                                       |

    - [ ] limit effort good idea?

  - [x] `metric-as-objective.md` | M      | anytime; also the substrate for drift-detection / roi-measurement                                   |
  - [>] `sqlite-store.md`        | M      | triggered: when scheduler-daemon or approval-ui adds a second writer                                |
  - [>] `core-as-package.md`     | S      | triggered: when a second real installation exists (the `__version__` first step is worth doing now) |

- [x] Minor

  - LLM wrapper has no retry/timeout
  - REPL dies on any command exception
  - no tests — though with --fake-llm the deterministic test harness is essentially already built and unused

- [x] Check the website domain pack and backlog tasks for adjustments needed because of the changes we made in the review

### 2026-06-26

- [x] Add a second domain pack "website". It starts with a minimal dummy website, then it consumes content from the internet either using web search or a specified list of pages. The LLM uses that content to improve the website. It may:

  - Edit content
  - but also change layout and design
  - create or remove new sub pages

  The exact goal for the LLM and how to improve the website is given by the user in config.

- [x] Git integration to version the materialized artifacts (needed for the website pack) [text](v%20done/260626%20-%20git-integration.md) — no git integration today; history lives only in the append-only JSONL log, materialized files keep latest version only.

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

  Variant 1: see tasks/v%20done/260621%20-%20domain-pack-template.md

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
