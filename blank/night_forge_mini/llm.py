"""One thin client wrapper around the model call (idea_2 seam).

Provider-agnostic: OpenRouter (default), Gemini, and Ollama all speak the
OpenAI-compatible chat API, so a single client switches by base_url + key + model.
This is also where a Langfuse/OTel callback would later be added — one call site.

`--fake-llm` skips the network entirely and returns a deterministic proposal, so the
whole loop runs and is testable with no key and no token spend.

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
from typing import Any

from .records import now_iso
from .tools.registry import Tool


class LLMError(RuntimeError):
    pass


class ModelWrapper:
    def __init__(self, provider: dict[str, Any], fake: bool = False):
        self.provider = provider
        self.fake = fake
        self._client = None
        self._schema_ok: bool | None = None  # None = untested, False = provider rejected it
        self._tool_trace: list[dict] = []    # spans of the current run_tools loop

    # The single one-shot model call site.
    def complete_json(self, system: str, user: str, schema: dict | None = None) -> dict[str, Any]:
        if self.fake:
            raise LLMError("complete_json called in fake mode; analyzer should branch earlier")
        return self._request_json(_messages(system, user), schema)

    # The agentic call site: a bounded READ-ONLY tool loop ending in the same JSON proposal.
    def run_tools(self, system: str, user: str, tools: list[Tool],
                  schema: dict | None = None, max_steps: int = 6,
                  result_cap: int = 16_000) -> dict[str, Any]:
        if self.fake:
            raise LLMError("run_tools called in fake mode; analyzer should branch earlier")
        usable = {t.name: t for t in tools if t.available()}
        messages = _messages(system, user)
        if not usable:  # nothing to offer (e.g. keys missing) -> plain structured call
            return self._request_json(messages, schema)

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
                return _extract_json(msg.content or "")
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.function.name,
                                                          "arguments": tc.function.arguments}}
                                            for tc in calls]})
            for tc in calls:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": self._run_tool(usable, tc, result_cap)})

        # Step budget exhausted while still calling tools: force the proposal, no tools.
        messages.append({"role": "user",
                         "content": "Tool budget exhausted - return the final JSON proposal now."})
        return self._request_json(messages, schema)

    def take_tool_trace(self) -> list[dict]:
        """Return and clear the spans of the tool calls made since the last take."""
        trace, self._tool_trace = self._tool_trace, []
        return trace

    def _run_tool(self, usable: dict[str, Tool], tc, cap: int) -> str:
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
        result = result[:cap]
        span = {"tool": name, "args": args, "status": status, "chars": len(result),
                "start": start, "end": now_iso()}
        if status == "error":
            span["detail"] = result[:200]
        self._tool_trace.append(span)
        return result

    def _request_json(self, messages: list[dict], schema: dict | None) -> dict[str, Any]:
        """One completion that must yield JSON — native `response_format: json_schema`
        when given (and the provider takes it), tolerant extraction otherwise."""
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
                return _extract_json(resp.choices[0].message.content or "")
            except Exception as e:
                if not _param_rejected(e):
                    raise
                self._schema_ok = False  # this provider can't take response_format -> plain from now on

        resp = client.chat.completions.create(**kwargs)
        return _extract_json(resp.choices[0].message.content or "")

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


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parse — models sometimes wrap JSON in prose or code fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"model did not return valid JSON: {e}\n---\n{text[:500]}")
    raise LLMError(f"no JSON found in model output:\n{text[:500]}")
