"""What a pass consumed — summed per backend, stored on the analysis record, printed by the
CLI (claude-code-backend-refinements §5 + roi-measurement step 1)."""
import json
from types import SimpleNamespace

from night_forge_mini.backends import ClaudeCodeBackend, HttpBackend, RoutedBackend
from night_forge_mini.backends.claude_code import MCP_NAME
from night_forge_mini.cli import usage_line
from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.pack import Action, Pack
from night_forge_mini.tools.registry import Tool

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}


def completion( content=None, tool_calls=None, usage=None ):
  from openai.types.chat import ChatCompletion
  msg = {'role': 'assistant', 'content': content}
  if tool_calls:
    msg['tool_calls'] = tool_calls
  body = {'id': 'r', 'object': 'chat.completion', 'created': 0, 'model': 'm',
          'choices': [{'index': 0, 'finish_reason': 'tool_calls' if tool_calls else 'stop',
                       'message': msg}]}
  if usage:
    body['usage'] = usage
  return ChatCompletion.model_validate(body)


def tokens( prompt, out, cached=None ):
  u = {'prompt_tokens': prompt, 'completion_tokens': out, 'total_tokens': prompt + out}
  if cached is not None:
    u['prompt_tokens_details'] = {'cached_tokens': cached}
  return u


def http( *responses ):
  script = list(responses)
  b = HttpBackend(PROVIDER)
  b._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
    create=lambda **kw: script.pop(0))))
  return b


def read_tool():
  return Tool(name='read', description='r', run=lambda: 'text',
              params={'type': 'object', 'properties': {}})


# --- per backend ---------------------------------------------------------------

def test_http_sums_every_call_of_a_pass_and_a_take_resets():
  call = [{'id': 't', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]
  b = http(completion(tool_calls=call, usage=tokens(1000, 50, cached=0)),
           completion('{"finding": "f", "actions": []}', usage=tokens(1200, 300, cached=900)))
  b.run_tools('s', 'u', [read_tool()])
  assert b.take_usage() == {'calls': 2, 'input_tokens': 2200, 'cached_tokens': 900,
                            'output_tokens': 350}
  assert b.take_usage() == {}


def test_a_provider_that_reports_no_usage_leaves_tokens_unknown_not_zero():
  b = http(completion('{"score": 1}'))
  b.complete_json('s', 'u')
  assert b.take_usage() == {'calls': 1}


def cli_result( **extra ):
  return {'type': 'result', 'is_error': False, 'result': '{"finding": "f", "actions": []}',
          'total_cost_usd': 0.0412,
          'usage': {'input_tokens': 10, 'cache_creation_input_tokens': 2000,
                    'cache_read_input_tokens': 30000, 'output_tokens': 800}, **extra}


def cli( tmp_path, out ):
  return ClaudeCodeBackend(Config(raw={'claudeCode': {}}, root=tmp_path),
                           runner=lambda cmd, prompt, timeout: (out, 0, ''))


def test_a_cli_turn_counts_all_three_input_parts_and_the_list_price( tmp_path ):
  init = {'type': 'system', 'subtype': 'init',
          'mcp_servers': [{'name': MCP_NAME, 'status': 'connected'}]}
  b = cli(tmp_path, '\n'.join(json.dumps(e) for e in (init, cli_result())))
  b.run_tools('s', 'u', [read_tool()])
  assert b.take_usage() == {'calls': 1, 'input_tokens': 32010, 'cached_tokens': 30000,
                            'output_tokens': 800, 'cost_usd': 0.0412}


def test_a_one_shot_cli_turn_is_counted_too( tmp_path ):
  b = cli(tmp_path, json.dumps(cli_result(structured_output={'score': 7})))
  b.complete_json('s', 'u', schema={'type': 'object'})
  assert b.take_usage()['cost_usd'] == 0.0412


def test_a_routed_backend_sums_both_routes( tmp_path ):
  agent = http(completion('{"finding": "f", "actions": []}', usage=tokens(100, 10)))
  judge = cli(tmp_path, json.dumps(cli_result(structured_output={'score': 7})))
  r = RoutedBackend(agent, judge)
  r.run_tools('s', 'u', [])
  r.complete_json('s', 'u', schema={'type': 'object'})
  u = r.take_usage()
  assert u['calls'] == 2 and u['input_tokens'] == 32110 and u['cost_usd'] == 0.0412


# --- in the loop -----------------------------------------------------------------

class Metered:
  """A backend whose usage the test controls."""
  fake = False

  def __init__( self ):
    self.pending = {}

  def take_tool_trace( self ):
    return []

  def take_usage( self ):
    u, self.pending = self.pending, {}
    return u

  def label( self ):
    return 'metered'


class Inbox:
  name = 'stub'

  def fetch( self, seen ):
    return [{'id': 's1', 'text': 'x', 'source': 'x'}] if 's1' not in seen else []


def test_the_pass_records_its_usage_and_not_a_failed_passs_leftovers( tmp_path ):
  model = Metered()
  model.pending = {'calls': 9}                       # left behind by a pass that raised

  def analyze( m, *, goal, snippets, history ):
    m.pending = {'calls': 2, 'input_tokens': 5000}   # this pass, judge included
    return {'finding': 'f', 'metric': {}, 'actions': []}

  ok = Action(name='a', risk_level='low', reversible=True, run=lambda t, p: {'status': 'ok'})
  cfg = Config(raw={'paths': {'log': 'log.jsonl'}, 'allow_list': [], 'recent_runs': 5},
               root=tmp_path)
  eng = Engine(cfg, Pack(domain='t', goal='g', connector=Inbox(), actions={'a': ok},
                         analyze=analyze), fake_llm=True)
  eng.model = model
  r = eng.run_once()
  assert r['usage'] == {'calls': 2, 'input_tokens': 5000}
  analysis = [x for x in eng.store.all() if x.type == 'analysis'][0]
  assert analysis.payload['usage'] == {'calls': 2, 'input_tokens': 5000}


def test_the_usage_line_shows_only_what_was_reported():
  assert usage_line({'calls': 3, 'input_tokens': 45200, 'cached_tokens': 38000,
                     'output_tokens': 1900, 'cost_usd': 0.0812}) == \
    '3 call(s) · 45.2k in (38.0k cached) · 1.9k out · $0.0812'
  assert usage_line({'calls': 1}) == '1 call(s)'
