"""The Claude Code backend — the agent CLI on the user's own subscription, no API key.

This is the backend that inverts the loop. Every other one is an endpoint we drive: we
call, run the tool it asked for, feed the result back. The CLI is an AGENT — we hand it a
prompt and it runs the whole tool loop itself, reaching our tools over MCP
(`mcp_server.py`) in a second process. So `run_tools` here does not iterate; it starts a
turn and reads back what happened.

Two roles, one object (see the Decisions section of tasks/backlog/claude-code-backend.md):
  run_tools      the agentic analyze pass -> the CLI
  complete_json  a one-shot call, e.g. an LLM-judged metric -> the cheap HTTP provider

A judge metric is a single small call returning one number; paying a process spawn plus an
MCP handshake for it is disproportionate, and the CLI has no structured-output parameter to
constrain it with. The split falls exactly on the two methods, so no pack changes.

CAUTION, the failure that matters: when the tools do not load, the agent does not fail — it
ANSWERS, from an artifact it invents, and the reply looks normal. So a turn is REFUSED
unless the CLI's own init event reports our MCP server connected. Our actions auto-run under
git-recoverable, which makes an invented proposal worse here than in a chat sidebar.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any

from ..records import now_iso
from .base import LLMError, _extract_json

MCP_NAME = "nfm"                     # how our server is named to the CLI
MCP_PREFIX = f"mcp__{MCP_NAME}__"    # how the CLI namespaces our tool names


class ClaudeCodeBackend:
    """`base.Backend` over the local `claude` CLI."""

    fake = False

    def __init__(self, cfg, one_shot=None, runner=None):
        self._block = block = cfg.get("claudeCode") or {}
        self.deploy = str(getattr(cfg, "root", "") or os.getcwd())
        self.bin = str(block.get("bin") or "claude")
        self.model = str(block.get("model") or "")
        self.timeout = int(block.get("timeout") or 300)
        self._one_shot = one_shot            # the cheap backend for judge-style calls
        self._run = runner or _run_cli       # injectable so the parser is testable
        self._tool_trace: list[dict] = []
        self._server_cmd = ""              # resolved per turn; named in the refusal

    # -- the two roles ---------------------------------------------------------

    def run_tools(self, system: str, user: str, tools: list,
                  schema: dict | None = None, **kwargs) -> dict[str, Any]:
        """One CLI turn. `tools` is used for its NAMES only — the callables live in this
        process and the agent cannot reach them; it reaches equivalents over MCP."""
        names = [f"{MCP_PREFIX}{t.name}" for t in tools if t.available()]
        if not names:
            # A connected server offering NOTHING passes the check below while leaving the
            # agent exactly as blind as a failed one — and a blind agent answers anyway.
            # Refuse here, where the cause is still legible (a pack that declares no
            # `analyze_tools`, or every tool missing its key).
            raise LLMError("the Claude Code backend was given no usable tools: the pack "
                           "declares none, or none is available. An agent with no tools "
                           "does not fail, it invents — so the turn is refused instead.")
        out, code, err = self._run(self._command(names, system), user, self.timeout)
        turn = self._parse(out)

        if not turn["connected"]:
            raise LLMError(
                "the Claude Code turn had no tools: our MCP server did not report as "
                "connected, so nothing in an answer would come from this deploy. The tool "
                f"server starts as: {self._server_cmd} "
                f"(exit {code}){' - ' + err.strip()[:300] if err.strip() else ''}")
        if turn["text"] == "":
            raise LLMError(f"the Claude Code CLI returned nothing (exit {code})"
                           f"{' - ' + err.strip()[:300] if err.strip() else ''}")

        self._tool_trace.extend(turn["spans"])
        return _extract_json(turn["text"])

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict[str, Any]:
        if self._one_shot is None:
            raise LLMError(
                "no one-shot backend configured for the Claude Code backend: a single "
                "small call (an LLM-judged metric) should go to a cheap provider, not a "
                "CLI turn. Configure `providers` + `provider` alongside `backend`.")
        return self._one_shot.complete_json(system, user, schema)

    def take_tool_trace(self) -> list[dict]:
        trace, self._tool_trace = self._tool_trace, []
        return trace

    def label(self) -> str:
        return f"claudeCode:{self.model or 'default'}"

    # -- the process -----------------------------------------------------------

    def _command(self, allowed: list[str], system: str) -> list[str]:
        """The argument list. Passed as a LIST so the executable starts directly — no
        shell, no quoting rules to get wrong.

        `--system-prompt` REPLACES the CLI's own: this turn is an analyze pass for a deploy,
        not a coding session, and the pack's prompt is what explains that an action is JSON
        to return rather than a tool to call. Dropping it (as the first version did) left
        the agent diagnosing the artifact correctly and then refusing to answer, because
        nothing had told it how to."""
        cmd = [self.bin, "-p",
               # plain `json` returns only the final text; the stream is what carries the
               # tool calls we log as spans
               "--output-format", "stream-json", "--verbose",
               # keep the user's own CLAUDE.md and memory out of the turn: this agent needs
               # the deploy's tools, not the machine's coding setup
               "--setting-sources", "",
               # built-in Read/Edit/Bash off. The website pack's artifact IS files, but they
               # must be written through our actions (gate, constraints, git), never by the
               # agent reaching the disk itself.
               "--tools", "",
               "--mcp-config", self._mcp_config(), "--strict-mcp-config",
               "--system-prompt", system]
        if allowed:
            cmd += ["--allowedTools", ",".join(allowed)]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def _mcp_config(self) -> str:
        """Our tool server, inline. FORWARD SLASHES ONLY: a Windows path would put `\\x`
        in the JSON, which is not a valid escape — the CLI then reads the argument as a
        FILE NAME and stops with "file not found"."""
        deploy = self.deploy.replace("\\", "/")
        python = self._python_bin()
        self._server_cmd = f"{python} -m night_forge_mini.mcp_server {deploy}"
        return json.dumps({"mcpServers": {MCP_NAME: {
            "command": python,
            "args": ["-m", "night_forge_mini.mcp_server", deploy],
            "env": {"PYTHONPATH": deploy},
        }}}, ensure_ascii=False)

    def _python_bin(self) -> str:
        """The interpreter that runs our tool server.

        `sys.executable` is NOT automatically it. grid-view lost a day to this exact shape
        in PHP: the tool server was started with `PHP_BINARY`, which under mod_php is the
        APACHE binary, so the server never came up — and the agent, left with no tools,
        answered from a board it invented, tabs and ticket numbers included. Once this
        engine is embedded (mod_wsgi, a frozen exe — see run-triggers/library-embed.md)
        `sys.executable` is the host binary in exactly the same way, and in some embedded
        contexts it is empty. So it is trusted only when it looks like an interpreter."""
        configured = str(self._block.get("pythonBin") or "").strip()
        if configured:
            return configured.replace("\\", "/")

        exe = sys.executable or ""
        if exe and "python" in os.path.basename(exe).lower():
            return exe.replace("\\", "/")

        found = shutil.which("python") or shutil.which("python3")
        if found:
            return found.replace("\\", "/")
        raise LLMError("cannot find the python interpreter that runs the tool server "
                       f"(sys.executable is {exe or 'empty'!r}, which is not one) — set "
                       "claudeCode.pythonBin in config.json")

    # -- the answer ------------------------------------------------------------

    def _parse(self, out: str) -> dict:
        """The stream is one JSON object per line. Keep what the loop needs — whether our
        tools loaded, the tool calls (as our span shape) and the final text — and drop the
        rest (banner, usage records, rate-limit events)."""
        spans: list[dict] = []
        pending: dict[str, dict] = {}      # tool_use id -> its span, awaiting the result
        text, connected = "", False
        stamp = now_iso()                  # the stream carries no per-event timestamps

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")

            if kind == "system" and msg.get("subtype") == "init":
                connected = any(s.get("name") == MCP_NAME and s.get("status") == "connected"
                                for s in msg.get("mcp_servers") or [])
            elif kind == "assistant":
                for block in (msg.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        span = {"tool": _plain(str(block.get("name") or "")),
                                "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                                "status": "ok", "chars": 0,
                                "start": stamp, "end": stamp}
                        spans.append(span)
                        pending[str(block.get("id") or "")] = span
            elif kind == "user":
                for block in (msg.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        span = pending.pop(str(block.get("tool_use_id") or ""), None)
                        if span is None:
                            continue
                        body = _result_text(block.get("content"))
                        span["chars"] = len(body)
                        if block.get("is_error"):
                            span["status"] = "error"
                            span["detail"] = body[:200]
            elif kind == "result":
                text = str(msg.get("result") or "")

        return {"text": text, "spans": spans, "connected": connected}


def _plain(name: str) -> str:
    """`mcp__nfm__read_page` -> `read_page`, so a span reads the same whichever backend
    produced it."""
    return name[len(MCP_PREFIX):] if name.startswith(MCP_PREFIX) else name


def _result_text(content: Any) -> str:
    """A tool result arrives as a string or as content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text") or "" for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _run_cli(cmd: list[str], prompt: str, timeout: int) -> tuple[str, int, str]:
    """Start the CLI and read it out. The prompt goes over STDIN: a Windows command line
    is length-limited and a long one would be silently truncated.

    `subprocess.run` drains both pipes for us, so there is no deadlock to hand-manage, and
    it kills the child on timeout — an orphan would keep reaching this deploy through the
    MCP server long after the run is gone."""
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=_work_dir())
    except FileNotFoundError as e:
        raise LLMError(f"could not start the Claude Code CLI ({cmd[0]}): {e}") from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"the Claude Code turn exceeded {timeout}s and was stopped") from e
    return p.stdout or "", p.returncode, p.stderr or ""


def _work_dir() -> str:
    """A directory of its own, kept empty, so the CLI finds no project it might read as
    context. Everything it may touch it reaches through our tools."""
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "nfm-agent-work")
    os.makedirs(d, exist_ok=True)
    return d
