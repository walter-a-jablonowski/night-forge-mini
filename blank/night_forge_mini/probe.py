"""`probe` — does this deploy's model setup work, checked in a minute instead of a pass.

"OpenAI-compatible" is a promise every provider keeps slightly differently, and so far each
live pass on a new one found its own quirk: Gemini 3 dropped a tool turn without its
thought_signature, an OpenRouter route answered 400 at random, Gemini's free tier allows 5
requests a minute. A supervised analyze pass is an expensive way to learn that. The probe
makes the two calls a pass depends on, with a known answer, against each configured route:

  one-shot  complete_json with a schema: does a constrained JSON answer come back?
  agent     run_tools with one probe tool: does the model call it, and does the turn
            survive being sent back (the provider state echo), and does the answer hold?

Every check is a fresh random word the model can only know by doing it right. A failure is
reported as the check's result, never raised: the point is to see ALL of what is wrong.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from .backends import ClaudeCodeBackend, HttpBackend, RoutedBackend
from .tools.registry import Tool

SCHEMA = {"type": "object", "properties": {"word": {"type": "string"}},
          "required": ["word"]}
SYSTEM = ('You are a connectivity check. Answer with a JSON object whose "word" field holds '
          'the word asked for, nothing else.')
# The task names the FIELD, never a JSON template: live 2026-10-11, haiku under the CLI's
# --json-schema answered `Return {"word": "x"}` with word = '{"word": "x"}' — the schema
# answer is already that object, and a template invites nesting it once more.


def probe(model) -> list[dict[str, Any]]:
    """One row per check: {role, label, ok, secs, detail}."""
    if isinstance(model, RoutedBackend):
        routes = [("agent", model.agent), ("one-shot", model.one_shot)]
    else:
        routes = [("agent", model), ("one-shot", model)]
    return [_check(role, backend) for role, backend in routes]


def _check(role: str, backend) -> dict[str, Any]:
    row = {"role": role, "label": backend.label(), "ok": False, "secs": 0.0}
    if role == "agent" and isinstance(backend, ClaudeCodeBackend):
        # its tools are the PACK's, served by our MCP server from the deploy — there is no
        # probe tool to hand it; a real `run-once` is the check for this route
        row.update(ok=None, detail="not probed: the CLI reaches the pack's own tools over "
                                   "MCP - `run-once` checks this route")
        return row
    word = secrets.token_hex(4)
    start = time.monotonic()
    try:
        if role == "agent":
            got, detail = _agent(backend, word)
        else:
            got, detail = _one_shot(backend, word)
        row.update(ok=got == word, detail=detail if got == word
                   else f"answered {got!r}, expected {word!r}" + (f" - {detail}" if detail else ""))
    except Exception as e:  # noqa: BLE001 - a failed check is a result, not a crash
        row["detail"] = f"{type(e).__name__}: {e}"[:300]
    row["secs"] = round(time.monotonic() - start, 1)
    return row


def _one_shot(backend, word: str) -> tuple[Any, str]:
    result = backend.complete_json(SYSTEM, f"The word is {word}.", schema=SCHEMA)
    return result.get("word"), _structured(backend)


def _agent(backend, word: str) -> tuple[Any, str]:
    tool = Tool(name="probe_word", description="Returns the word to answer with.",
                run=lambda: word, params={"type": "object", "properties": {}})
    result = backend.run_tools(SYSTEM, "Call the probe_word tool once; the word is what "
                                       "it returns.", tools=[tool], schema=SCHEMA, max_steps=3)
    calls = [s for s in backend.take_tool_trace() if s.get("tool") == "probe_word"]
    if not calls:
        # the right word is unknowable without the call: this is the model answering
        # blind, the failure that matters most
        return result.get("word"), "the tool was never called"
    return result.get("word"), f"tool called {len(calls)}x, the turn was accepted back"


def _structured(backend) -> str:
    if isinstance(backend, ClaudeCodeBackend):
        return "structured output: --json-schema"
    if not isinstance(backend, HttpBackend):
        return ""
    if backend.schema_ok is False:
        return "structured output: REJECTED by the provider - plain JSON + retry instead"
    if "api.anthropic.com" in str(backend.provider.get("base_url", "")):
        # accepted without error and NOT applied (Anthropic's docs): only the prompt and
        # the JSON retry hold the format there
        return "structured output: ignored by this endpoint - plain JSON + retry instead"
    return "structured output: native"
