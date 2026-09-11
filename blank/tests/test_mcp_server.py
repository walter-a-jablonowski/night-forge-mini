"""The stdio MCP bridge: the same pack tools an in-process backend calls, served to an
agent that runs in its own process."""
import io
import json

from night_forge_mini.mcp_server import handle, serve, tool_defs
from night_forge_mini.tools.registry import Tool


def read_tool( fn=None ):
  return Tool(name='read_page', description='read one page',
              run=fn or (lambda path='': f'SOURCE OF {path}'),
              params={'type': 'object', 'properties': {'path': {'type': 'string'}},
                      'required': ['path']})


def drive( lines, tools ):
  """Run the server over a scripted stdin; returns the parsed responses."""
  out = io.StringIO()
  serve(io.StringIO('\n'.join(json.dumps(m) for m in lines)), out, tools)
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
  assert handle(request(1, 'nope'), {})['error']['code'] == -32601


def test_garbage_on_stdin_does_not_kill_the_server():
  """stdin is another process's stdout; a stray line must not take the tools down."""
  out = io.StringIO()
  serve(io.StringIO('not json\n\n' + json.dumps(request(1, 'ping')) + '\n'), out, [read_tool()])
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
