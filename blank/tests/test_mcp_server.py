"""The stdio MCP bridge: the same pack tools an in-process backend calls, served to an
agent that runs in its own process."""
import io
import json

from night_forge_mini.mcp_server import ToolPass, handle, main, serve, tool_defs
from night_forge_mini.tools.pass_budget import PassBudget
from night_forge_mini.tools.registry import Tool


def read_tool( fn=None ):
  return Tool(name='read_page', description='read one page',
              run=fn or (lambda path='': f'SOURCE OF {path}'),
              params={'type': 'object', 'properties': {'path': {'type': 'string'}},
                      'required': ['path']})


def drive( lines, tools, **pass_opts ):
  """Run the server over a scripted stdin; returns the parsed responses."""
  out = io.StringIO()
  serve(io.StringIO('\n'.join(json.dumps(m) for m in lines)), out, ToolPass(tools, **pass_opts))
  return [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]


def request( mid, method, **params ):
  return {'jsonrpc': '2.0', 'id': mid, 'method': method, 'params': params}


def test_handshake_echoes_the_client_protocol_version():
  # the CLI and this server only have to agree with each other; echoing avoids failing a
  # handshake over a version we would have supported anyway
  out = drive([request(1, 'initialize', protocolVersion='2024-11-05')], [read_tool()])
  assert out[0]['result']['protocolVersion'] == '2024-11-05'
  assert out[0]['result']['capabilities'] == {'tools': {}}


def test_tools_list_exposes_the_registry_schema_unchanged():
  """`Tool.params` IS the schema an MCP client wants — the registry was already built for
  a model-facing consumer, so nothing is translated."""
  tool = read_tool()
  out = drive([request(1, 'tools/list')], [tool])
  listed = out[0]['result']['tools'][0]
  assert listed['name'] == 'read_page'
  assert listed['inputSchema'] == tool.params
  assert tool_defs([tool])[0]['description'] == 'read one page'


def test_tools_call_runs_the_tool_and_returns_its_text():
  out = drive([request(1, 'tools/call', name='read_page', arguments={'path': 'index.html'})],
              [read_tool()])
  assert out[0]['result']['content'][0]['text'] == 'SOURCE OF index.html'
  assert not out[0]['result'].get('isError')


def test_a_failing_tool_is_an_error_RESULT_not_a_protocol_error():
  """The agent must see the reason and be able to correct itself, exactly as the
  in-process backend turns a tool exception into an error string."""
  def boom( path='' ):
    raise ValueError('no such page')

  out = drive([request(1, 'tools/call', name='read_page', arguments={'path': 'x'})],
              [read_tool(boom)])
  assert out[0]['result']['isError'] is True
  assert 'no such page' in out[0]['result']['content'][0]['text']
  assert 'error' not in out[0]                        # the CALL failed, the protocol did not


def test_unknown_tool_names_what_is_available():
  out = drive([request(1, 'tools/call', name='create_page', arguments={})], [read_tool()])
  text = out[0]['result']['content'][0]['text']
  assert 'unknown tool create_page' in text and 'read_page' in text


def test_a_notification_is_never_answered():
  # answering a notification is a protocol error; only the request gets a response
  out = drive([{'jsonrpc': '2.0', 'method': 'notifications/initialized'},
               request(2, 'ping')], [read_tool()])
  assert [m['id'] for m in out] == [2]


def test_unknown_method_is_a_jsonrpc_error():
  assert handle(request(1, 'nope'), ToolPass([]))['error']['code'] == -32601


def test_garbage_on_stdin_does_not_kill_the_server():
  """stdin is another process's stdout; a stray line must not take the tools down."""
  out = io.StringIO()
  serve(io.StringIO('not json\n\n' + json.dumps(request(1, 'ping')) + '\n'), out,
        ToolPass([read_tool()]))
  assert [json.loads(l)['id'] for l in out.getvalue().splitlines() if l.strip()] == [1]


def test_an_unavailable_tool_is_not_offered_at_all():
  """A keyed tool with no key must be absent, not broken — the same rule `run_tools`
  applies when it builds `usable`. Caught live: web_search was listed without a key."""
  keyed = Tool(name='web_search', description='search', run=lambda query='': 'hits',
               requires=['DEFINITELY_UNSET_KEY_FOR_TEST'],
               params={'type': 'object', 'properties': {'query': {'type': 'string'}}})

  out = drive([request(1, 'tools/list'),
               request(2, 'tools/call', name='web_search', arguments={'query': 'x'})],
              [read_tool(), keyed])
  assert [t['name'] for t in out[0]['result']['tools']] == ['read_page']
  assert out[1]['result']['isError'] is True          # and it is not callable either


# --- the pass bounds, enforced here because the agent owns the loop --------

def call( mid, path ):
  return request(mid, 'tools/call', name='read_page', arguments={'path': path})


def texts( out ):
  return [m['result']['content'][0]['text'] for m in out]


def test_a_repeated_read_is_answered_from_the_pass_cache():
  """Live, on the Claude Code backend: one pass read index.html five times. The HTTP
  backend already answered a repeat with a pointer; the MCP path re-ran it every time."""
  ran = []
  out = drive([call(1, 'index.html'), call(2, 'index.html')],
              [read_tool(lambda path='': ran.append(path) or f'SOURCE OF {path}')])
  assert ran == ['index.html']                        # the tool itself ran once
  assert 'already read above' in texts(out)[1]
  assert not out[1]['result'].get('isError')          # a pointer, not a failure


def test_the_call_budget_stops_reading_but_not_the_pass():
  """`analyze_tool_steps` was ignored on this backend — swallowed by **kwargs. Past the
  budget the agent is told to answer, rather than the turn being cut off unanswered."""
  out = drive([call(1, 'a'), call(2, 'b'), call(3, 'c')], [read_tool()], max_calls=2)
  assert texts(out)[:2] == ['SOURCE OF a', 'SOURCE OF b']
  assert out[2]['result']['isError'] is True
  assert 'final JSON' in texts(out)[2]


def test_a_cached_repeat_spends_no_budget():
  out = drive([call(1, 'a'), call(2, 'a'), call(3, 'b')], [read_tool()], max_calls=2)
  assert texts(out)[2] == 'SOURCE OF b'


def test_results_are_bounded_by_the_pass_budget():
  out = drive([call(1, 'a'), call(2, 'b')], [read_tool(lambda path='': 'X' * 80)],
              budget=PassBudget(cap=1000, remaining=100))
  assert len(texts(out)[0]) == 80
  assert 'trimmed' in texts(out)[1] and len(texts(out)[1]) < 80


def test_main_takes_the_bounds_from_its_command_line( tmp_path, monkeypatch ):
  """The backend hands the pack's numbers over as arguments — the only channel into a
  process the CLI starts. Checked end to end through main(), on a minimal deploy."""
  import sys
  (tmp_path / 'config.json').write_text('{}', encoding='utf-8')
  (tmp_path / 'domain_pack.py').write_text(
    'from types import SimpleNamespace\n'
    'from night_forge_mini.tools.registry import Tool\n'
    'def build_pack(cfg):\n'
    '  return SimpleNamespace(analyze_tools=[Tool(name="read_page", description="d",\n'
    '    run=lambda path="": "Y" * 50, params={"type": "object"})])\n', encoding='utf-8')
  lines = [call(i, p) for i, p in enumerate(['a', 'b', 'c'], 1)]
  out = io.StringIO()
  monkeypatch.setattr(sys, 'stdin', io.StringIO('\n'.join(json.dumps(m) for m in lines)))
  monkeypatch.setattr(sys, 'stdout', out)
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr(sys, 'path', list(sys.path))    # main() prepends the deploy dir
  monkeypatch.delitem(sys.modules, 'domain_pack', raising=False)

  main([str(tmp_path), '--max-calls', '2', '--result-cap', '30', '--result-budget', '1000'])

  got = texts([json.loads(l) for l in out.getvalue().splitlines() if l.strip()])
  assert 'trimmed' in got[0]                          # --result-cap reached the budget
  assert 'final JSON' in got[2]                       # --max-calls reached the pass
  sys.modules.pop('domain_pack', None)
