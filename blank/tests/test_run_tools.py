"""HttpBackend.run_tools: bounded read-only tool loop ending in a structured proposal."""
from types import SimpleNamespace

from night_forge_mini.backends import LLMError
from night_forge_mini.backends.http import HttpBackend
from night_forge_mini.pack import proposal_schema
from night_forge_mini.tools.registry import Tool

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}
REPLY = '{"finding": "f", "actions": []}'
SCHEMA = proposal_schema(['add_entry'])


def tool_call( name, arguments, id_='tc1' ):
  return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=arguments))


def response( content=None, tool_calls=None ):
  msg = SimpleNamespace(content=content, tool_calls=tool_calls)
  return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


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
