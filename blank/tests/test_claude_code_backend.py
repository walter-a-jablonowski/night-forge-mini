"""ClaudeCodeBackend: the agent CLI turn, parsed back into our shape.

The CLI is driven through an injected runner, so everything here — the invented-answer
guard, the span translation, the role split — is verified without spawning anything.
"""
import json

import pytest

from night_forge_mini.backends import LLMError
from night_forge_mini.backends.claude_code import MCP_NAME, ClaudeCodeBackend
from night_forge_mini.config import Config
from night_forge_mini.tools.registry import Tool


def cfg( tmp_path, **block ):
  raw = {'provider': 'p',
         'providers': {'p': {'model': 'm', 'base_url': 'http://x', 'api_key_env': 'K'}},
         'paths': {'log': 'data/log.jsonl'}, 'allow_list': [], 'recent_runs': 5,
         'claudeCode': block}
  return Config(raw=raw, root=tmp_path)


def stream( *events ):
  return '\n'.join(json.dumps(e) for e in events) + '\n'


def init( connected=True ):
  return {'type': 'system', 'subtype': 'init',
          'mcp_servers': [{'name': MCP_NAME, 'status': 'connected' if connected else 'failed'}]}


def tool_use( tid, name, args ):
  return {'type': 'assistant',
          'message': {'content': [{'type': 'tool_use', 'id': tid,
                                   'name': f'mcp__{MCP_NAME}__{name}', 'input': args}]}}


def tool_result( tid, text, is_error=False ):
  return {'type': 'user',
          'message': {'content': [{'type': 'tool_result', 'tool_use_id': tid,
                                   'content': [{'type': 'text', 'text': text}],
                                   'is_error': is_error}]}}


def final( text ):
  return {'type': 'result', 'result': text}


def backend( tmp_path, out, code=0, err='', one_shot=None, **block ):
  runner = lambda cmd, prompt, timeout: (out, code, err)
  b = ClaudeCodeBackend(cfg(tmp_path, **block), one_shot=one_shot, runner=runner)
  b.last_cmd = None
  def spy( cmd, prompt, timeout ):
    b.last_cmd, b.last_prompt = cmd, prompt
    return (out, code, err)
  b._run = spy
  return b


def read_tool():
  return Tool(name='read_page', description='read', run=lambda path='': path,
              params={'type': 'object', 'properties': {'path': {'type': 'string'}}})


PROPOSAL = '{"finding": "f", "actions": []}'


# --- the invented-answer guard ---------------------------------------------

def test_a_turn_without_our_tools_is_refused_however_much_text_came_back( tmp_path ):
  """The failure this guard exists for: with no tools the agent does not fail, it ANSWERS
  from an artifact it invents, and the reply looks perfectly normal. Our actions auto-run
  under git-recoverable, so an invented proposal must never reach the gate."""
  b = backend(tmp_path, stream(init(connected=False), final(PROPOSAL)))
  with pytest.raises(LLMError) as e:
    b.run_tools('sys', 'usr', tools=[read_tool()])
  assert 'connected' in str(e.value)


def test_an_empty_turn_reports_the_exit_code_and_stderr( tmp_path ):
  b = backend(tmp_path, stream(init()), code=1, err='boom')
  with pytest.raises(LLMError) as e:
    b.run_tools('sys', 'usr', tools=[read_tool()])
  assert 'exit 1' in str(e.value) and 'boom' in str(e.value)


# --- the answer, in our shape ----------------------------------------------

def test_tool_calls_become_our_spans_with_the_mcp_prefix_stripped( tmp_path ):
  b = backend(tmp_path, stream(
    init(),
    tool_use('t1', 'read_page', {'path': 'index.html'}),
    tool_result('t1', 'SOURCE'),
    tool_use('t2', 'read_page', {'path': 'gone.html'}),
    tool_result('t2', 'error: no such page', is_error=True),
    final(PROPOSAL)))

  assert b.run_tools('sys', 'usr', tools=[read_tool()]) == {'finding': 'f', 'actions': []}
  spans = b.take_tool_trace()
  # a span must read the same whichever backend produced it
  assert [(s['tool'], s['status'], s['chars']) for s in spans] == [
    ('read_page', 'ok', 6), ('read_page', 'error', 19)]
  assert spans[0]['args'] == {'path': 'index.html'}
  assert 'no such page' in spans[1]['detail']
  assert b.take_tool_trace() == []                    # popped, not accumulated


def test_a_prose_wrapped_proposal_still_parses( tmp_path ):
  # the CLI has no response_format, so the proposal comes back as text
  b = backend(tmp_path, stream(init(), final(f'Here you go:\n```json\n{PROPOSAL}\n```')))
  assert b.run_tools('sys', 'usr', tools=[read_tool()])['finding'] == 'f'


# --- the command ------------------------------------------------------------

def test_the_command_disables_built_ins_and_the_users_own_settings( tmp_path ):
  b = backend(tmp_path, stream(init(), final(PROPOSAL)), model='opus')
  b.run_tools('SYSTEM PROMPT', 'USER CONTEXT', tools=[read_tool()])
  cmd = b.last_cmd

  assert cmd[:2] == ['claude', '-p']
  assert '--verbose' in cmd                                   # stream-json needs it
  assert cmd[cmd.index('--setting-sources') + 1] == ''        # no CLAUDE.md / memory
  assert cmd[cmd.index('--tools') + 1] == ''                  # no built-in Read/Edit/Bash
  assert '--strict-mcp-config' in cmd
  assert cmd[cmd.index('--model') + 1] == 'opus'
  assert cmd[cmd.index('--allowedTools') + 1] == f'mcp__{MCP_NAME}__read_page'
  assert b.last_prompt == 'USER CONTEXT'                      # prompt over stdin


def test_the_pack_system_prompt_reaches_the_cli( tmp_path ):
  """Caught live: the first version built the command without it. The agent read the
  site, diagnosed the broken link correctly — and then refused to answer, because nothing
  had told it that an action is JSON to return rather than a tool to call."""
  b = backend(tmp_path, stream(init(), final(PROPOSAL)))
  b.run_tools('ACTIONS ARE NOT TOOLS', 'usr', tools=[read_tool()])
  assert b.last_cmd[b.last_cmd.index('--system-prompt') + 1] == 'ACTIONS ARE NOT TOOLS'


def test_the_mcp_config_is_json_with_forward_slashes( tmp_path ):
  """A Windows path would put `\\x` in the JSON, which is not a valid escape — the CLI
  then reads the argument as a FILE NAME and stops with "file not found"."""
  b = backend(tmp_path, stream(init(), final(PROPOSAL)))
  b.run_tools('sys', 'usr', tools=[read_tool()])
  raw = b.last_cmd[b.last_cmd.index('--mcp-config') + 1]

  parsed = json.loads(raw)                                    # must be parseable JSON
  server = parsed['mcpServers'][MCP_NAME]
  assert '\\' not in raw
  assert server['args'][:2] == ['-m', 'night_forge_mini.mcp_server']
  assert server['env']['PYTHONPATH'] == server['args'][2]     # the deploy dir


def test_an_unavailable_tool_is_not_allow_listed( tmp_path ):
  keyed = Tool(name='web_search', description='s', run=lambda query='': '',
               requires=['DEFINITELY_UNSET_KEY_FOR_TEST'], params={'type': 'object'})
  b = backend(tmp_path, stream(init(), final(PROPOSAL)))
  b.run_tools('sys', 'usr', tools=[read_tool(), keyed])
  assert 'web_search' not in b.last_cmd[b.last_cmd.index('--allowedTools') + 1]


# --- the role split ---------------------------------------------------------

def test_a_one_shot_call_goes_to_the_cheap_backend_not_a_cli_turn( tmp_path ):
  """A judged metric is one small call returning a number; a process spawn plus an MCP
  handshake for it is disproportionate, and the CLI cannot constrain it with a schema."""
  class Cheap:
    def complete_json( self, system, user, schema=None ):
      return {'score': 7}

  b = backend(tmp_path, stream(init(), final(PROPOSAL)), one_shot=Cheap())
  assert b.complete_json('sys', 'usr')['score'] == 7
  assert b.last_cmd is None                            # the CLI was never started


def test_a_one_shot_call_without_a_cheap_backend_says_what_to_configure( tmp_path ):
  b = backend(tmp_path, stream(init(), final(PROPOSAL)))
  with pytest.raises(LLMError) as e:
    b.complete_json('sys', 'usr')
  assert 'provider' in str(e.value)


def test_label_names_the_backend_and_model( tmp_path ):
  assert backend(tmp_path, '', model='opus').label() == 'claudeCode:opus'
  assert backend(tmp_path, '').label() == 'claudeCode:default'


def test_a_turn_with_no_usable_tools_is_refused_before_it_starts( tmp_path ):
  """A connected server offering NOTHING passes the connected check while leaving the agent
  as blind as a failed one. The kb pack declared no analyze_tools at first — exactly this."""
  keyed = Tool(name='web_search', description='s', run=lambda query='': '',
               requires=['DEFINITELY_UNSET_KEY_FOR_TEST'], params={'type': 'object'})
  b = backend(tmp_path, stream(init(), final(PROPOSAL)))

  for offered in ([], [keyed]):
    with pytest.raises(LLMError) as e:
      b.run_tools('sys', 'usr', tools=offered)
    assert 'no usable tools' in str(e.value)
  assert b.last_cmd is None                            # the CLI was never started
