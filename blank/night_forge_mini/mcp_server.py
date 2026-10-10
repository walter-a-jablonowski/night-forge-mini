"""Stdio MCP server over a pack's analyze tools — the bridge to an agent backend.

An agent backend (the Claude Code CLI) runs the tool loop in its OWN process, so it cannot
be handed Python callables. It is given this module as a subprocess instead: it speaks
JSON-RPC over stdin/stdout, and this process rebuilds the pack and serves the same
`analyze_tools` the in-process backend would have called directly. One tool definition,
two ways of reaching it.

Run it from a deploy directory:

    python -m night_forge_mini.mcp_server

STDOUT IS THE PROTOCOL. Nothing may print to it but a JSON-RPC message — a stray `print`
in a tool corrupts the stream and the agent loses its tools, which (see the backlog task)
does not make it fail but makes it invent. Diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

from .tools.pass_budget import RESULT_BUDGET, RESULT_CAP, PassBudget
from .tools.registry import Tool

PROTOCOL_VERSION = "2025-06-18"     # used only when the client names none
SERVER_INFO = {"name": "night-forge-mini", "version": "0.3.0"}


def tool_defs(tools: list[Tool]) -> list[dict]:
    """Our tools in MCP's shape. `Tool.params` is already a JSON schema, which is exactly
    what `inputSchema` wants — the registry was built for the model, and an MCP client is
    just another model-facing consumer."""
    return [{"name": t.name,
             "description": t.description,
             "inputSchema": t.params or {"type": "object", "properties": {}}}
            for t in tools]


class ToolPass:
    """One analyze pass as this server sees it. The process lives exactly one CLI turn, so
    its state IS the pass state — which lets it apply the same hygiene the HTTP backend
    applies inside its own loop (`PassBudget`), plus the step bound the pack asked for.

    `max_calls` counts tool EXECUTIONS, not model turns: this side of the protocol cannot
    see turns, so a turn that reads three files in parallel spends three. A repeat answered
    from the pass cache spends nothing — it costs the model a sentence, not a read.
    None = unbounded, for running the server by hand."""

    def __init__(self, tools: list[Tool], max_calls: int | None = None,
                 budget: PassBudget | None = None):
        # Offer only what is actually usable, exactly as the in-process backend does: a
        # keyed tool with no key must not appear in the list at all. Advertising one the
        # agent then cannot call wastes a step and reads to the model as a broken tool
        # rather than an absent one.
        self.tools = {t.name: t for t in tools if t.available()}
        self.calls_left = max_calls
        self.budget = budget or PassBudget()

    def call(self, name: str, args: dict) -> dict:
        """Run one tool. A failure is reported as an MCP error RESULT, not a protocol
        error: the agent should see what went wrong and be able to correct itself, exactly
        as the in-process backend lets a tool failure become an error string."""
        tool = self.tools.get(name)
        if tool is None:
            return _text(f"unknown tool {name}; available: "
                         f"{', '.join(sorted(self.tools)) or '(none)'}", error=True)
        note = self.budget.repeat(name, args)
        if note is not None:
            return _text(note)
        if self.calls_left is not None:
            if self.calls_left <= 0:
                return _text("tool budget exhausted for this pass - stop reading and return "
                             "the final JSON proposal now", error=True)
            self.calls_left -= 1
        try:
            result = str(tool.run(**args))
        except Exception as e:  # noqa: BLE001 - the agent gets the reason and may retry
            return _text(f"error: {type(e).__name__}: {e}", error=True)
        self.budget.remember(name, args, len(result))
        return _text(self.budget.take(result))


def handle(message: dict, tool_pass: ToolPass) -> dict | None:
    """One JSON-RPC request -> one response, or None for a notification (which must NOT
    be answered; a response to a notification is a protocol error)."""
    method = message.get("method", "")
    mid = message.get("id")
    if mid is None:
        return None                                   # notification, e.g. initialized

    if method == "initialize":
        params = message.get("params") or {}
        return _ok(mid, {
            # echo the client's version when it names one: the CLI and this server only
            # have to agree, and echoing avoids a handshake failure over a version we
            # would have supported anyway
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "tools/list":
        return _ok(mid, {"tools": tool_defs(list(tool_pass.tools.values()))})
    if method == "tools/call":
        params = message.get("params") or {}
        args = params.get("arguments")
        return _ok(mid, tool_pass.call(str(params.get("name") or ""),
                                       args if isinstance(args, dict) else {}))
    if method == "ping":
        return _ok(mid, {})
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin: TextIO, stdout: TextIO, tool_pass: ToolPass) -> None:
    """The loop. Line-delimited JSON in, line-delimited JSON out, until stdin closes."""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue                                  # not ours to interpret; stay quiet
        if not isinstance(message, dict):
            continue
        response = handle(message, tool_pass)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def _ok(mid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _text(text: str, error: bool = False) -> dict:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if error:
        result["isError"] = True
    return result


def main(argv: list[str] | None = None) -> None:
    """Build the deploy's pack and serve its analyze tools for one pass.

    The deploy directory may be given as the first argument: an agent backend runs the CLI
    in an EMPTY working directory (so it finds no project to read as context), which means
    this subprocess cannot rely on inheriting a useful cwd. The pass bounds come from the
    backend, which got them from the pack — the same numbers the HTTP backend enforces.
    """
    import os
    from .config import load

    ap = argparse.ArgumentParser(prog="night_forge_mini.mcp_server")
    ap.add_argument("deploy", nargs="?", default="")
    ap.add_argument("--max-calls", type=int, default=None)
    ap.add_argument("--result-cap", type=int, default=RESULT_CAP)
    ap.add_argument("--result-budget", type=int, default=RESULT_BUDGET)
    opts = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if opts.deploy:
        os.chdir(opts.deploy)
    sys.path.insert(0, os.getcwd())                   # the merged deploy's domain_pack
    import domain_pack                                # noqa: PLC0415 - deploy-local

    pack = domain_pack.build_pack(load("config.json"))
    tools = list(pack.analyze_tools)
    if not tools:
        print("night-forge-mini MCP: the pack offers no analyze tools", file=sys.stderr)
    serve(sys.stdin, sys.stdout,
          ToolPass(tools, max_calls=opts.max_calls,
                   budget=PassBudget(cap=opts.result_cap, remaining=opts.result_budget)))


if __name__ == "__main__":
    main()
