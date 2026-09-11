"""The OpenAI-compatible HTTP backend — the one every configured provider uses.

Provider-agnostic: OpenRouter (default), Gemini, and Ollama all speak the same chat API,
so a single client switches by base_url + key + model. This is also where a Langfuse/OTel
callback would later be added — one call site.

One of several backends behind `base.Backend`; `--fake-llm` and the Claude Code CLI are
siblings, not flags on this one.

Structured output: pass a JSON schema (see `pack.proposal_schema`) and it is sent as
`response_format: json_schema` so the provider constrains the output natively. If a
provider rejects the parameter (some Ollama models), we fall back to plain completion +
tolerant extraction — and remember the rejection, so it costs one extra call ever.

Agentic analyze (`run_tools`): instead of one one-shot completion, the model may iterate
with READ-ONLY tools (function calling) — read a KB entry in full, fetch a page — under a
hard step budget, then emit the same structured proposal. Write actions still only happen
through the gate; the tools handed in here must never mutate anything. Every tool call is
recorded (`take_tool_trace`) so the Engine can log it as a span under the analysis record.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..records import now_iso
from ..tools.registry import Tool
from .base import LLMError, _extract_json


JSON_ATTEMPTS = 3    # one call plus two retries when the reply will not parse

_JSON_FIX = ("Your previous reply was not valid JSON ({error}). Send the SAME proposal "
             "again as STRICT JSON only - no prose, no code fences, no trailing commas, "
             "and escape every quote and newline inside string values.")



@dataclass
class _ToolBudget:
    """One agentic pass's result budget. `cap` bounds a single result, `remaining` the sum
    of all of them; `seen` maps an already-answered call to the size it returned.

    Both exist because a result is not paid for once: every later step resends the whole
    conversation, so one big read is billed again on each of them (measured 4-6x). The sum
    is also what decides whether a long pass still fits in the window at all."""
    cap: int
    remaining: int
    seen: dict[tuple[str, str], int] = field(default_factory=dict)

    def take(self, result: str) -> str:
        """What of `result` may go into the prompt — trimmed, and SAID to be trimmed, so
        the model knows it is looking at part of a file rather than a short one."""
        allowed = min(self.cap, max(self.remaining, 0))
        if len(result) <= allowed:
            self.remaining -= len(result)
            return result
        dropped = len(result) - allowed
        note = f"\n… trimmed: {dropped:,} more characters (per-pass result budget reached)"
        self.remaining -= allowed
        return result[:max(allowed - len(note), 0)] + note


class HttpBackend:
    """`base.Backend` over an OpenAI-compatible chat endpoint. The agentic loop is driven
    HERE — this backend calls the model, runs the tool it asked for, and feeds the result
    back; a backend that is itself an agent does the opposite."""

    fake = False        # this one really calls; `--fake-llm` selects FakeBackend instead

    def __init__(self, provider: dict[str, Any]):
        self.provider = provider
        self._client = None
        self._schema_ok: bool | None = None  # None = untested, False = provider rejected it
        self._tool_trace: list[dict] = []    # spans of the current run_tools loop

    # The single one-shot model call site.
    def complete_json(self, system: str, user: str, schema: dict | None = None) -> dict[str, Any]:
        return self._request_json(_messages(system, user), schema)

    # The agentic call site: a bounded READ-ONLY tool loop ending in the same JSON proposal.
    def run_tools(self, system: str, user: str, tools: list[Tool],
                  schema: dict | None = None, max_steps: int = 6,
                  result_cap: int = 16_000,
                  result_budget: int = 40_000) -> dict[str, Any]:
        usable = {t.name: t for t in tools if t.available()}
        messages = _messages(system, user)
        if not usable:  # nothing to offer (e.g. keys missing) -> plain structured call
            return self._request_json(messages, schema)

        # Per-pass result hygiene. Every step resends the whole conversation, so a tool
        # result is not paid for once but once per remaining step — measured at 4-6x on the
        # website deploy. `result_cap` bounds one result; this bounds the SUM, which is what
        # decides whether a long pass still fits at all.
        budget = _ToolBudget(cap=result_cap, remaining=result_budget)

        client = self._ensure_client()
        defs = [{"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.params or {"type": "object", "properties": {}}}}
                for t in usable.values()]
        for _ in range(max_steps):
            resp = client.chat.completions.create(model=self.provider["model"],
                                                  messages=messages, temperature=0.2, tools=defs)
            msg = resp.choices[0].message
            calls = getattr(msg, "tool_calls", None)
            if not calls:  # model is done reading -> its answer is the proposal
                content = msg.content or ""
                try:
                    return _extract_json(content)
                except LLMError as e:
                    # It finished reading and got the content right, only the JSON wrong —
                    # hand the error back rather than lose every tool read that led here.
                    self._trace_json_retry(e)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": _JSON_FIX.format(error=e)})
                    return self._request_json(messages, schema)
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name,
                                                          "arguments": tc.function.arguments}}
                                            for tc in calls]})
            for tc in calls:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": self._run_tool(usable, tc, budget)})

        # Step budget exhausted while still calling tools: force the proposal, no tools.
        messages.append({"role": "user",
                         "content": "Tool budget exhausted - return the final JSON proposal now."})
        return self._request_json(messages, schema)

    def take_tool_trace(self) -> list[dict]:
        """Return and clear the spans of the tool calls made since the last take."""
        trace, self._tool_trace = self._tool_trace, []
        return trace

    def _run_tool(self, usable: dict[str, Tool], tc, budget: "_ToolBudget") -> str:
        """Run one requested tool; any failure becomes an error STRING the model sees
        (and can react to), never an exception that kills the run. Each call is traced."""
        name = tc.function.name
        start = now_iso()
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        # The model asked for something it already has. The tools in this loop are
        # READ-ONLY and nothing writes during a pass, so the answer cannot have changed —
        # re-sending the body would only pay for it again on every remaining step.
        key = (name, json.dumps(args, sort_keys=True))
        if key in budget.seen:
            note = (f"(already read above in this pass — see the earlier {name} result; "
                    "it has not changed)")
            self._tool_trace.append({"tool": name, "args": args, "status": "ok",
                                     "chars": budget.seen[key], "sent": len(note),
                                     "cached": True, "start": start, "end": now_iso()})
            return note

        try:
            tool = usable.get(name)
            if tool is None:
                # Name what IS callable: models otherwise retry the same phantom name, or
                # give up on the work entirely (a pack's ACTION names are the usual mixup).
                raise LLMError(f"unknown tool {name}; callable tools are: "
                               f"{', '.join(sorted(usable)) or '(none)'}")
            result, status = str(tool.run(**args)), "ok"
        except Exception as e:  # noqa: BLE001 - the model gets the reason and may retry
            result, status = f"error: {type(e).__name__}: {e}", "error"
        full = len(result)
        sent = budget.take(result)
        # `chars` stays the HONEST size: the prompt may have got less, but the trace is the
        # audit trail of what the tool actually returned, and must not shrink with it.
        span = {"tool": name, "args": args, "status": status, "chars": full,
                "start": start, "end": now_iso()}
        if len(sent) != full:
            span["sent"] = len(sent)
        if status == "error":
            span["detail"] = result[:200]
        self._tool_trace.append(span)
        if status == "ok":
            budget.seen[(name, json.dumps(args, sort_keys=True))] = full
        return sent

    def _request_json(self, messages: list[dict], schema: dict | None) -> dict[str, Any]:
        """A completion that must yield JSON — native `response_format: json_schema` when
        given (and the provider takes it), tolerant extraction otherwise.

        Retried on a PARSE failure: models emit a stray delimiter or a bad escape often
        enough when the payload is a long source file, and by then the pass has already
        paid for its tool reads — throwing it away over one formatting slip is the
        expensive choice. The bad reply and the parse error go back as the correction,
        which is the only context that makes the retry worth anything."""
        msgs = list(messages)
        for attempt in range(JSON_ATTEMPTS):
            text = self._raw_json_reply(msgs, schema)
            try:
                return _extract_json(text)
            except LLMError as e:
                if attempt == JSON_ATTEMPTS - 1:
                    raise
                self._trace_json_retry(e)
                msgs = msgs + [{"role": "assistant", "content": text},
                               {"role": "user", "content": _JSON_FIX.format(error=e)}]
        raise LLMError("unreachable")  # pragma: no cover - the loop always returns or raises

    def _raw_json_reply(self, messages: list[dict], schema: dict | None) -> str:
        """The model call itself: structured output when the provider accepts it."""
        client = self._ensure_client()
        kwargs: dict[str, Any] = {"model": self.provider["model"], "messages": messages,
                                  "temperature": 0.2}
        if schema is not None and self._schema_ok is not False:
            try:
                resp = client.chat.completions.create(
                    **kwargs,
                    response_format={"type": "json_schema",
                                     "json_schema": {"name": "proposal", "schema": schema}})
                self._schema_ok = True
                return resp.choices[0].message.content or ""
            except Exception as e:
                if not _param_rejected(e):
                    raise
                self._schema_ok = False  # this provider can't take response_format -> plain from now on

        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def _trace_json_retry(self, error: Exception) -> None:
        """A retry is an extra model call inside the analyze step, so it belongs in the
        same span list the Engine logs — an invisible retry is an invisible cost."""
        ts = now_iso()
        self._tool_trace.append({"tool": "json_retry", "args": {}, "status": "error",
                                 "chars": 0, "start": ts, "end": ts,
                                 "detail": str(error)[:200]})

    def label(self) -> str:
        return f'{self.provider["name"]}:{self.provider["model"]}'

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai package not installed; `pip install -r requirements.txt` or use --fake-llm") from e
        key = os.environ.get(self.provider.get("api_key_env", ""), "") or "no-key"
        # The SDK already retries transient failures (connection errors, 429, 5xx) with
        # backoff — we only bound the per-request time (its 600s default is far too long
        # for a loop pass) and make both knobs per-provider config.
        self._client = OpenAI(base_url=self.provider["base_url"], api_key=key,
                              timeout=float(self.provider.get("timeout", 120)),
                              max_retries=int(self.provider.get("max_retries", 2)))
        return self._client


def _messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _param_rejected(e: Exception) -> bool:
    """True when the provider rejected the request itself (4xx: unknown/unsupported
    parameter) — the only case where retrying without `response_format` makes sense.
    Auth, network and server errors must propagate, not trigger a blind retry."""
    return getattr(e, "status_code", None) in (400, 422)
