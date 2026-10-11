"""HttpBackend.run_tools: bounded read-only tool loop ending in a structured proposal."""
from types import SimpleNamespace

import pytest

from night_forge_mini.backends import LLMError
from night_forge_mini.backends.http import HttpBackend
from night_forge_mini.pack import proposal_schema
from night_forge_mini.tools.registry import Tool

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}
REPLY = '{"finding": "f", "actions": []}'
SCHEMA = proposal_schema(['add_entry'])


def tool_call( name, arguments, id_='tc1', **extra ):
  """`extra` = provider fields the SDK keeps on the object, e.g. Gemini's `extra_content`."""
  return {'id': id_, 'type': 'function', 'function': {'name': name, 'arguments': arguments},
          **extra}


def response( content=None, tool_calls=None, finish=None, **extra ):
  """A REAL `ChatCompletion`, not a stand-in: a stand-in carries only the fields the test
  author thought of, so it can neither hold a provider's extra state nor prove that the
  code reads the object the SDK actually returns (see long-run §7)."""
  from openai.types.chat import ChatCompletion
  msg = {'role': 'assistant', 'content': content, **extra}
  if tool_calls:
    msg['tool_calls'] = tool_calls
  return ChatCompletion.model_validate({
    'id': 'r', 'object': 'chat.completion', 'created': 0, 'model': 'm',
    'choices': [{'index': 0, 'finish_reason': finish or ('tool_calls' if tool_calls else 'stop'),
                 'message': msg}]})


def make_wrapper( responses ):
  """Wrapper whose stub client pops one scripted response per create() call."""
  calls = []
  script = list(responses)

  def create( **kw ):
    calls.append(kw)
    return script.pop(0)

  w = HttpBackend(PROVIDER)
  w._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  return w, calls


def read_tool( fn=None ):
  return Tool(name='read_entry', description='read one entry',
              run=fn or (lambda id='': f'FULL TEXT OF {id}'),
              params={'type': 'object', 'properties': {'id': {'type': 'string'}},
                      'required': ['id']})


def test_tool_loop_runs_tool_then_returns_proposal():
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "vpn"}')]),
    response(content=REPLY),
  ])
  out = w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert out == {'finding': 'f', 'actions': []}

  assert calls[0]['tools'][0]['function']['name'] == 'read_entry'
  tool_msg = calls[1]['messages'][-1]
  assert tool_msg['role'] == 'tool' and tool_msg['content'] == 'FULL TEXT OF vpn'

  trace = w.take_tool_trace()
  assert [(s['tool'], s['status']) for s in trace] == [('read_entry', 'ok')]
  assert w.take_tool_trace() == []                    # popped, not accumulated


def test_unknown_tool_and_crashing_tool_become_error_results():
  def boom( id='' ):
    raise ValueError('kaput')

  w, calls = make_wrapper([
    response(tool_calls=[tool_call('nope', '{}', 'a'), tool_call('read_entry', 'not json', 'b')]),
    response(content=REPLY),
  ])
  out = w.run_tools('sys', 'usr', tools=[read_tool(boom)], schema=SCHEMA)
  assert out == {'finding': 'f', 'actions': []}

  results = [m['content'] for m in calls[1]['messages'] if m.get('role') == 'tool']
  assert results[0].startswith('error:')              # unknown tool
  assert 'kaput' in results[1]                        # exception -> error text, loop survives
  assert all(s['status'] == 'error' for s in w.take_tool_trace())


def test_unknown_tool_error_says_an_action_is_not_callable():
  """Measured on a fresh deploy: 13 of 42 tool calls in two passes were ACTION names —
  `add_asset` alone 10 times — and the site ended with 20 image searches and no images.
  Naming the callable tools is not enough; the model needs telling where the name DOES
  belong, or it abandons the work instead of re-routing it."""
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('add_asset', '{}', 'a')]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool(lambda id='': 'body')], schema=SCHEMA)

  result = [m['content'] for m in calls[1]['messages'] if m.get('role') == 'tool'][0]
  assert 'actions array' in result          # where it should have gone
  assert 'final answer' in result


def test_unknown_tool_error_names_the_callable_tools():
  """A model that invents a tool name (a pack's ACTION names are the usual mixup) must be
  told what it CAN call, or it retries the phantom name and abandons the work."""
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('create_page', '{}', 'a')]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool(lambda id='': 'body')], schema=SCHEMA)

  result = [m['content'] for m in calls[1]['messages'] if m.get('role') == 'tool'][0]
  assert 'unknown tool create_page' in result
  assert 'read_entry' in result                       # the offer, not just the refusal


def test_budget_exhausted_forces_final_schema_call():
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}')]),
    response(content=REPLY),                          # the forced finale
  ])
  out = w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA, max_steps=1)
  assert out == {'finding': 'f', 'actions': []}
  final = calls[1]
  assert 'tools' not in final                         # no more tool calls allowed
  assert final['response_format']['json_schema']['schema'] is SCHEMA
  assert 'budget' in final['messages'][-1]['content']


def test_no_available_tools_degrades_to_plain_structured_call():
  keyed = Tool(name='keyed', description='needs key', run=lambda: '', requires=['NOPE_MISSING'])
  w, calls = make_wrapper([response(content=REPLY)])
  out = w.run_tools('sys', 'usr', tools=[keyed], schema=SCHEMA)
  assert out == {'finding': 'f', 'actions': []}
  assert len(calls) == 1 and 'tools' not in calls[0]
  assert calls[0]['response_format']['json_schema']['schema'] is SCHEMA


def test_tool_result_is_capped():
  big = lambda id='': 'x' * 50_000
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}')]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool(big)], schema=SCHEMA, result_cap=16_000)
  tool_msg = [m for m in calls[1]['messages'] if m.get('role') == 'tool'][0]
  assert len(tool_msg['content']) == 16_000


# --- a malformed JSON reply must not throw the whole pass away -------------

BROKEN = '{"finding": "f", "actions": [{"name": "add_entry", "target": "t",}]}'   # trailing comma


def test_malformed_json_after_reading_is_retried_with_the_error():
  """The expensive part (the tool reads) is already paid for when the model emits its
  proposal — losing the pass to one formatting slip wastes all of it (try/website, twice)."""
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "vpn"}')]),
    response(content=BROKEN),                         # done reading, but invalid JSON
    response(content=REPLY),                          # retry succeeds
  ])
  out = w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert out == {'finding': 'f', 'actions': []}

  # the retry carries the bad reply back plus what was wrong with it
  last = calls[-1]['messages']
  assert last[-2]['role'] == 'assistant' and last[-2]['content'] == BROKEN
  assert 'not valid JSON' in last[-1]['content']


def test_json_retry_is_bounded_and_then_raises():
  w, calls = make_wrapper([response(content=BROKEN)] * 4)
  try:
    w.complete_json('sys', 'usr', schema=SCHEMA)
    assert False, 'should have raised'
  except LLMError as e:
    assert 'did not return valid JSON' in str(e)
  assert len(calls) == 3                              # first attempt + 2 retries, no more


def test_json_retries_are_visible_in_the_trace():
  w, _ = make_wrapper([response(content=BROKEN), response(content=REPLY)])
  assert w.complete_json('sys', 'usr', schema=SCHEMA) == {'finding': 'f', 'actions': []}
  spans = [s for s in w.take_tool_trace() if s['tool'] == 'json_retry']
  assert len(spans) == 1 and spans[0]['status'] == 'error'


# --- per-pass result hygiene (analyze-context-amplification.md) -------------

def test_identical_tool_call_is_answered_from_the_pass_cache():
  """run-a257a9c6 read style.css twice; the body was then re-sent on every later step.
  Analyze tools are read-only and nothing writes during a pass, so a repeat is redundant."""
  ran = []
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}', 'c1')]),
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}', 'c2')]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool(lambda id='': ran.append(id) or 'BODY ' * 20)],
              schema=SCHEMA)

  assert len(ran) == 1                                # the tool itself ran once
  results = [m['content'] for m in calls[-1]['messages'] if m.get('role') == 'tool']
  assert 'BODY' in results[0]
  assert 'already' in results[1].lower()              # the repeat gets a pointer, not the body
  spans = w.take_tool_trace()
  assert len(spans) == 2 and spans[1].get('cached') is True


def test_tool_results_are_bounded_by_a_total_budget():
  """`result_cap` bounds one result; nothing bounded the SUM, which is what eventually
  stops a pass from fitting."""
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}', 'c1')]),
    response(tool_calls=[tool_call('read_entry', '{"id": "b"}', 'c2')]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool(lambda id='': 'X' * 80)], schema=SCHEMA,
              result_budget=100)

  results = [m['content'] for m in calls[-1]['messages'] if m.get('role') == 'tool']
  assert len(results[0]) == 80                        # fits
  assert len(results[1]) < 80 and 'trimmed' in results[1].lower()
  # the LOG keeps the honest size even when the prompt got less
  spans = w.take_tool_trace()
  assert spans[1]['chars'] == 80 and spans[1]['sent'] < 80


def test_a_transient_upstream_400_in_the_TOOL_LOOP_is_retried():
  """Pass 6 of the long run died outright on `400 Provider returned error` from a flaky
  OpenRouter upstream. The earlier 400 fix only covered the JSON completion path — the
  agentic loop's own call had no handling at all, so one bad route killed a whole pass."""
  class Upstream(Exception):
    status_code = 400
    def __init__( self ):
      super().__init__("Error code: 400 - {'error': {'message': 'Provider returned error', "
                       "'metadata': {'provider_name': 'AtlasCloud'}}}")

  state = {'n': 0}
  script = [response(content=REPLY)]

  def create( **kw ):
    state['n'] += 1
    if state['n'] == 1:
      raise Upstream()               # the route we happened to get is unhealthy
    return script.pop(0)

  from types import SimpleNamespace
  from night_forge_mini.backends.http import HttpBackend
  w = HttpBackend(PROVIDER)
  w._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

  out = w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert out == {'finding': 'f', 'actions': []}          # the pass survives
  assert state['n'] == 2                                 # retried exactly once
  assert [s['tool'] for s in w.take_tool_trace()] == ['provider_retry']   # and it is visible


def test_provider_state_on_the_assistant_turn_is_echoed_back():
  """Gemini 3 attaches a `thought_signature` to every tool call and REQUIRES it back on the
  next request — measured live: `400 Function call is missing a thought_signature` at step
  2, so no agentic pass could run on Gemini. The turn used to be rebuilt field by field,
  which kept only what we knew about; OpenRouter's reasoning details are the same shape."""
  signature = {'google': {'thought_signature': 'SIG'}}
  w, calls = make_wrapper([
    response(tool_calls=[tool_call('read_entry', '{"id": "a"}', extra_content=signature)],
             reasoning_details=[{'type': 'reasoning.encrypted', 'data': 'R'}]),
    response(content=REPLY),
  ])
  w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)

  turn = [m for m in calls[1]['messages'] if m.get('role') == 'assistant'][0]
  assert turn['tool_calls'][0]['extra_content'] == signature
  assert turn['reasoning_details'] == [{'type': 'reasoning.encrypted', 'data': 'R'}]
  assert turn['content'] == '' and 'annotations' not in turn


# --- a reply cut off at the output limit (interchangeable-llms §3) ------------------

def test_a_cut_off_final_answer_is_reported_as_such_not_retried_as_bad_json():
  """A website proposal carries whole pages. Cut off, it used to read as a FORMAT error,
  and the retry asked for the same proposal again — which hit the same limit."""
  w, calls = make_wrapper([response(content='{"finding": "f", "actions": [{"payl',
                                    finish='length')])
  with pytest.raises(LLMError, match='cut off.*max_tokens'):
    w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert len(calls) == 1
  assert w.take_tool_trace() == []                       # no json_retry was spent


def test_a_cut_off_one_shot_reply_is_reported_without_a_retry():
  w, calls = make_wrapper([response(content='{"score": 7, "rea', finish='length')])
  with pytest.raises(LLMError, match='cut off'):
    w.complete_json('sys', 'usr', schema=SCHEMA)
  assert len(calls) == 1


# --- provider quirks as config (interchangeable-llms §5) --------------------------

def provider_wrapper( responses, **settings ):
  w, calls = make_wrapper(responses)
  w.provider = {**PROVIDER, **settings}
  return w, calls


def test_requests_carry_the_default_temperature_and_no_max_tokens():
  w, calls = provider_wrapper([response(content=REPLY)])
  w.complete_json('sys', 'usr')
  assert calls[0]['temperature'] == 0.2 and 'max_tokens' not in calls[0]


def test_a_null_temperature_is_not_sent_and_max_tokens_is_on_every_call():
  """Reasoning models refuse any temperature; their 400 says "not supported", which would
  also have switched structured output off by mistake."""
  w, calls = provider_wrapper([response(tool_calls=[tool_call('read_entry', '{"id": "a"}')]),
                               response(content=REPLY)],
                              temperature=None, max_tokens=32000)
  w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert all('temperature' not in c and c['max_tokens'] == 32000 for c in calls)


def test_the_transient_400_retry_can_be_switched_off_for_a_direct_provider():
  class Upstream(Exception):
    status_code = 400

  state = {'n': 0}

  def create( **kw ):
    state['n'] += 1
    raise Upstream('Provider returned error')

  w = HttpBackend({**PROVIDER, 'retry_transient_400': False})
  w._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  with pytest.raises(Upstream):
    w.run_tools('sys', 'usr', tools=[read_tool()], schema=SCHEMA)
  assert state['n'] == 1
