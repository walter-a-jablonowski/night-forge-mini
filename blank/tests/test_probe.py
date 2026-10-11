"""`probe`: the two calls a pass depends on, with a known answer, per configured route."""
import json
import re
from types import SimpleNamespace

from night_forge_mini.backends import ClaudeCodeBackend, HttpBackend, RoutedBackend
from night_forge_mini.cli import main
from night_forge_mini.config import Config
from night_forge_mini.probe import probe

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}


def completion( content=None, tool_calls=None, finish=None ):
  from openai.types.chat import ChatCompletion
  msg = {'role': 'assistant', 'content': content}
  if tool_calls:
    msg['tool_calls'] = tool_calls
  return ChatCompletion.model_validate({
    'id': 'r', 'object': 'chat.completion', 'created': 0, 'model': 'm',
    'choices': [{'index': 0, 'finish_reason': finish or ('tool_calls' if tool_calls else 'stop'),
                 'message': msg}]})


def provider( behaviour='good' ):
  """An HttpBackend over a scripted model: it calls the tool, then answers with what the
  tool returned — or misbehaves as asked."""
  def create( **kw ):
    msgs = kw['messages']
    if behaviour == 'cut':
      return completion('{"wo', finish='length')
    if 'tools' in kw:
      if behaviour == 'blind':
        return completion(json.dumps({'word': 'guessed'}))
      if msgs[-1]['role'] == 'tool':
        return completion(json.dumps({'word': msgs[-1]['content']}))
      return completion(tool_calls=[{'id': 't1', 'type': 'function',
                                     'function': {'name': 'probe_word', 'arguments': '{}'}}])
    word = re.search(r'The word is (\w+)', msgs[-1]['content']).group(1)
    return completion(json.dumps({'word': word}))

  b = HttpBackend(PROVIDER)
  b._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  return b


def test_a_working_provider_passes_both_checks():
  rows = probe(provider())
  assert [(r['role'], r['ok']) for r in rows] == [('agent', True), ('one-shot', True)]
  assert 'tool called 1x' in rows[0]['detail']
  assert rows[1]['detail'] == 'structured output: native'


def test_a_model_that_answers_without_calling_the_tool_fails():
  agent = probe(provider('blind'))[0]
  assert agent['ok'] is False and 'never called' in agent['detail']


def test_a_cut_off_reply_is_reported_not_raised():
  rows = probe(provider('cut'))
  assert all(r['ok'] is False and 'cut off' in r['detail'] for r in rows)


def test_routes_are_probed_separately_and_the_cli_agent_is_left_to_run_once( tmp_path ):
  def runner( cmd, prompt, timeout ):
    word = re.search(r'The word is (\w+)', prompt).group(1)
    return json.dumps({'type': 'result', 'is_error': False, 'result': '',
                       'structured_output': {'word': word}}), 0, ''

  cli = ClaudeCodeBackend(Config(raw={'claudeCode': {'model': 'haiku'}}, root=tmp_path),
                          runner=runner)
  rows = probe(RoutedBackend(cli, cli))
  assert rows[0]['ok'] is None and 'run-once' in rows[0]['detail']
  assert rows[1]['ok'] is True and rows[1]['label'] == 'claudeCode:haiku'
  assert '--json-schema' in rows[1]['detail']


def test_the_probe_command_needs_no_pack_and_knows_fake_is_nothing_to_probe( tmp_path, capsys ):
  cfg = tmp_path / 'config.json'
  cfg.write_text(json.dumps({'paths': {'log': 'log.jsonl'}}), encoding='utf-8')
  assert main(['--config', str(cfg), '--fake-llm', 'probe']) == 0
  assert 'nothing to probe' in capsys.readouterr().out
