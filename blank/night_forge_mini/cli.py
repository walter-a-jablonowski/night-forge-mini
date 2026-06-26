"""CLI over the log (idea_2 "Approval interface = CLI over the log").

Commands: run-once · inbox · approve <action_id> · reject <action_id> · trace <run_id>
Run with no command (or `shell`) for an interactive REPL session that loads the engine once
and dispatches the same operations in a loop. Every command prints a readable summary; the
JSONL log stays the source of truth.

Domain-agnostic: the one domain pack is loaded via `import domain_pack` (a package that
must sit next to night_forge_mini/ and expose `build_pack(cfg) -> Pack`). With no pack
present the core is intentionally not runnable — it tells you to drop one in.
"""
from __future__ import annotations

import argparse
import sys

from .config import load
from .env import load_dotenv
from .loop import Engine
from .records import DECISION, OUTCOME


def _load_pack():
    try:
        import domain_pack  # the single plugged-in domain (sits next to this package)
    except ImportError:
        print("No domain_pack found - copy a domain from /domains into this folder "
              "(the domain_pack/ package must sit next to night_forge_mini/).",
              file=sys.stderr)
        return None
    return domain_pack


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # load .env (cwd) before any provider key is read
    p = argparse.ArgumentParser(prog="night_forge_mini",
                                description="Self-improving closed-loop system (blank core + one domain pack)")
    p.add_argument("--config", default="config.json")
    p.add_argument("--fake-llm", action="store_true", help="deterministic offline analysis (no API key / tokens)")
    sub = p.add_subparsers(dest="cmd", required=False)  # no command -> interactive REPL
    sub.add_parser("run-once", help="run one loop pass")
    sub.add_parser("inbox", help="list pending actions awaiting approval")
    ap = sub.add_parser("approve", help="approve a pending action"); ap.add_argument("action_id")
    rj = sub.add_parser("reject", help="reject a pending action"); rj.add_argument("action_id")
    tr = sub.add_parser("trace", help="dump a run as a tree"); tr.add_argument("run_id")
    sub.add_parser("shell", help="interactive REPL session (loads the engine once)")

    args = p.parse_args(argv)

    domain_pack = _load_pack()
    if domain_pack is None:
        return 2

    cfg = load(args.config)
    pack = domain_pack.build_pack(cfg)
    eng = Engine(cfg, pack, fake_llm=args.fake_llm)

    if args.cmd in (None, "shell"):
        return _repl(eng)
    if args.cmd == "run-once":
        return _run_once(eng)
    if args.cmd == "inbox":
        return _inbox(eng)
    if args.cmd == "approve":
        return _verdict(eng.approve(args.action_id), "approved")
    if args.cmd == "reject":
        return _verdict(eng.reject(args.action_id), "rejected")
    if args.cmd == "trace":
        return _trace(eng, args.run_id)
    return 1


REPL_HELP = """commands:
  run                 run one loop pass (capture -> analyze -> propose -> gate)
  inbox               list pending actions awaiting approval
  approve <id|n>      approve a pending action (by action_id or inbox number)
  reject  <id|n>      reject a pending action (by action_id or inbox number)
  trace   <run_id>    dump a run as a tree
  help                show this help
  quit | exit         leave the session"""


def _resolve_ref(eng: Engine, ref: str) -> str | None:
    """Resolve an approve/reject argument: an inbox index (1-based) or a raw action_id."""
    if ref.isdigit():
        pend = eng.store.pending_actions()
        i = int(ref)
        return pend[i - 1]["action"]["action_id"] if 1 <= i <= len(pend) else None
    return ref


def _repl(eng: Engine) -> int:
    tag = "  [fake-llm]" if eng.model.fake else ""
    print(f"night_forge_mini interactive - domain: {eng.pack.domain}{tag}")
    print("type 'help' for commands, 'quit' to exit")
    while True:
        try:
            line = input("nfm> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd, rest = parts[0].lower(), parts[1:]
        if cmd in ("quit", "exit", "q"):
            break
        elif cmd in ("help", "h", "?"):
            print(REPL_HELP)
        elif cmd in ("run", "run-once"):
            _run_once(eng)
        elif cmd == "inbox":
            _inbox(eng)
        elif cmd in ("approve", "reject"):
            if not rest:
                print(f"usage: {cmd} <id|n>")
                continue
            aid = _resolve_ref(eng, rest[0])
            if aid is None:
                print(f"no pending action '{rest[0]}'")
            elif cmd == "approve":
                _verdict(eng.approve(aid), "approved")
            else:
                _verdict(eng.reject(aid), "rejected")
        elif cmd == "trace":
            if not rest:
                print("usage: trace <run_id>")
            else:
                _trace(eng, rest[0])
        else:
            print(f"unknown command: {cmd} (try 'help')")
    return 0


def _run_once(eng: Engine) -> int:
    r = eng.run_once()
    if r["status"] == "noop":
        print(f"nothing to do: {r['reason']}")
        return 0
    m = r["metric"] or {}
    metric_str = "  ".join(f"{k}={v}" for k, v in m.items()) if m else "(none)"
    print(f"run        : {r['run_id']}  (model: {r['model']})")
    print(f"captured   : {r['captured']} new artifact(s)")
    print(f"analysis   : {r['finding']}")
    print(f"metric     : {metric_str}")
    print("proposal   :")
    for item in r["ran"]:
        a = item["action"]
        res = item["res"].get("result", {})
        verb = "AUTO-RAN ok" if res.get("status", "ok") == "ok" else "AUTO-RAN FAILED"
        print(f"  {a['action_id']}  {a['name']:<18} [{a['risk_level']},rev={a['reversible']}]  -> {verb}  {res.get('detail','')}")
    for a in r["pending"]:
        print(f"  {a['action_id']}  {a['name']:<18} [{a['risk_level']},rev={a['reversible']}]  -> PENDING (needs approval)")
    if r["pending"]:
        print(f"{len(r['pending'])} pending - run `inbox` to review")
    _print_git(r.get("git"))
    return 0


def _print_git(git) -> None:
    """Render git commit result(s) from a run/verdict, if git versioning is on."""
    if not git:
        return
    items = git if isinstance(git, list) else [git]
    for gr in items:
        if not gr or gr.get("status") in ("skipped", "noop"):
            continue
        if gr.get("status") == "ok":
            push = f"  (push {gr['push']})" if "push" in gr else ""
            print(f"git        : committed {gr.get('detail','')}{push}")
        else:
            print(f"git        : {gr.get('status')} {gr.get('detail','')}")


def _inbox(eng: Engine) -> int:
    pend = eng.store.pending_actions()
    if not pend:
        print("inbox empty - no pending actions")
        return 0
    print(f"{len(pend)} pending action(s):")
    for v in pend:
        a = v["action"]
        print(f"\n  {a['action_id']}  ({v['run_id']})")
        print(f"    {a['name']} -> {a.get('target','')}   [{a.get('risk_level','?')}, reversible={a.get('reversible')}]")
        if a.get("rationale"):
            print(f"    why: {a['rationale']}")
        print(f"    approve: approve {a['action_id']}   |   reject: reject {a['action_id']}")
    return 0


def _verdict(res: dict, word: str) -> int:
    if res["status"] != "ok":
        print(f"error: {res['reason']}")
        return 1
    a = res["action"]
    inner = res["res"]
    if inner.get("ran"):
        result = inner.get("result", {})
        verb = "ran ok" if result.get("status", "ok") == "ok" else "ran FAILED"
        tail = f" -> {verb} ({result.get('detail','')})"
    else:
        tail = ""
    print(f"{a['action_id']} {word} [logged under {res['run_id']}]{tail}")
    _print_git(res.get("git"))
    return 0


def _trace(eng: Engine, run_id: str) -> int:
    recs = eng.store.by_run(run_id)
    if not recs:
        print(f"no such run {run_id}")
        return 1
    print(f"run {run_id}")
    tops = [r for r in recs if r.parent_id is None]
    children: dict[str, list] = {}
    for r in recs:
        if r.parent_id:
            children.setdefault(r.parent_id, []).append(r)
    for r in tops:
        _print_rec(r)
        if r.type == "proposal":
            for a in r.payload.get("actions", []):
                aid = a["action_id"]
                print(f"   - {aid} {a['name']} -> {a.get('target','')} [{a.get('risk_level')},rev={a.get('reversible')}]")
                for c in children.get(aid, []):
                    _print_rec(c, indent="       ")
    return 0


def _print_rec(r, indent: str = "  ") -> None:
    if r.type == "input":
        extra = f"{len(r.payload.get('snippet_ids', []))} artifact(s)"
    elif r.type == "analysis":
        extra = r.payload.get("finding", "")
    elif r.type == "proposal":
        extra = f"{len(r.payload.get('actions', []))} action(s)"
    elif r.type == DECISION:
        extra = f"{r.payload.get('verdict')} by {r.payload.get('by')}"
    elif r.type == OUTCOME:
        extra = f"{r.payload.get('status')} {r.payload.get('detail','')}"
    else:
        extra = ""
    print(f"{indent}{r.type:<9} {extra}")


if __name__ == "__main__":
    sys.exit(main())
