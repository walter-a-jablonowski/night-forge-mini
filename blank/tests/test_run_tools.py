"""ModelWrapper.run_tools: bounded read-only tool loop ending in a structured proposal."""
from types import SimpleNamespace

from night_forge_mini.llm import ModelWrapper
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

  w = ModelWrapper(PROVIDER)
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
