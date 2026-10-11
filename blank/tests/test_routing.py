"""Routing: the agent pass goes to `backend`, one-shot calls to `one_shot` (backends/routed.py).

The one-shot role was hard-wired to the HTTP provider on the Claude Code backend; these pin
that it is now a config choice, and that the old default still holds.
"""
import pytest

from night_forge_mini import backends
from night_forge_mini.backends import (ClaudeCodeBackend, FakeBackend, HttpBackend,
                                       RoutedBackend)
from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.pack import Pack

PROVIDERS = {'gemini': {'model': 'g-flash', 'base_url': 'http://g', 'api_key_env': 'G'},
             'openrouter': {'model': 'glm', 'base_url': 'http://o', 'api_key_env': 'O'}}


def cfg( tmp_path, **raw ):
  base = {'paths': {'log': 'data/log.jsonl'}, 'allow_list': [], 'recent_runs': 5}
  return Config(raw={**base, **raw}, root=tmp_path)


def build( tmp_path, name, **raw ):
  return backends.build(cfg(tmp_path, **raw), name)


# --- the default: unchanged behaviour ------------------------------------------

def test_http_without_one_shot_is_the_provider_itself_unwrapped( tmp_path ):
  """Unwrapped on purpose: one instance keeps what it learned (a rejected schema)."""
  b = build(tmp_path, 'http', provider='gemini', providers=PROVIDERS)
  assert isinstance(b, HttpBackend) and b.label() == 'gemini:g-flash'


def test_claude_code_still_judges_with_the_configured_provider_by_default( tmp_path ):
  b = build(tmp_path, 'claudeCode', provider='gemini', providers=PROVIDERS,
            claudeCode={'model': 'sonnet'})
  assert isinstance(b, RoutedBackend)
  assert isinstance(b.agent, ClaudeCodeBackend) and isinstance(b.one_shot, HttpBackend)
  assert b.label() == 'claudeCode:sonnet + one-shot gemini:g-flash'


# --- the new routes ----------------------------------------------------------

def test_a_subscription_only_deploy_needs_no_provider_at_all( tmp_path ):
  b = build(tmp_path, 'claudeCode', claudeCode={'model': 'sonnet'})
  assert isinstance(b, ClaudeCodeBackend)          # both kinds of call go to the CLI


def test_one_shot_claude_code_with_its_own_model( tmp_path ):
  b = build(tmp_path, 'claudeCode', provider='gemini', providers=PROVIDERS,
            one_shot='claudeCode', claudeCode={'model': 'sonnet', 'oneShotModel': 'haiku'})
  assert isinstance(b.one_shot, ClaudeCodeBackend)
  assert b.label() == 'claudeCode:sonnet + one-shot claudeCode:haiku'


def test_one_shot_claude_code_on_the_agents_model_is_not_wrapped( tmp_path ):
  b = build(tmp_path, 'claudeCode', provider='gemini', providers=PROVIDERS,
            one_shot='claudeCode', claudeCode={'model': 'sonnet'})
  assert isinstance(b, ClaudeCodeBackend)


def test_an_http_deploy_can_judge_with_another_provider( tmp_path ):
  b = build(tmp_path, 'http', provider='openrouter', one_shot='gemini', providers=PROVIDERS)
  assert b.label() == 'openrouter:glm + one-shot gemini:g-flash'


def test_an_http_deploy_can_judge_on_the_subscription( tmp_path ):
  b = build(tmp_path, 'http', provider='openrouter', one_shot='claudeCode',
            providers=PROVIDERS)
  assert isinstance(b.agent, HttpBackend) and isinstance(b.one_shot, ClaudeCodeBackend)


def test_an_unknown_route_names_what_is_valid( tmp_path ):
  with pytest.raises(ValueError, match="one_shot 'gpt'.*gemini, openrouter.*claudeCode"):
    build(tmp_path, 'http', provider='gemini', one_shot='gpt', providers=PROVIDERS)


def test_a_fake_deploy_is_never_routed_to_a_model( tmp_path ):
  b = build(tmp_path, 'fake', one_shot='claudeCode')
  assert isinstance(b, FakeBackend) and b.fake


# --- the router itself ---------------------------------------------------------

class Stub:
  fake = False

  def __init__( self, name ):
    self.name, self.calls, self.trace = name, [], [{'tool': f'{name}_span'}]

  def complete_json( self, system, user, schema=None ):
    self.calls.append(('complete_json', schema))
    return {'by': self.name}

  def run_tools( self, system, user, tools, schema=None, **bounds ):
    self.calls.append(('run_tools', bounds))
    return {'by': self.name}

  def take_tool_trace( self ):
    trace, self.trace = self.trace, []
    return trace

  def label( self ):
    return self.name


def test_each_kind_of_call_goes_to_its_own_backend_with_bounds_intact():
  agent, judge = Stub('agent'), Stub('judge')
  r = RoutedBackend(agent, judge)
  assert r.run_tools('s', 'u', [], None, max_steps=4, result_budget=9)['by'] == 'agent'
  assert r.complete_json('s', 'u', {'type': 'object'})['by'] == 'judge'
  assert agent.calls == [('run_tools', {'max_steps': 4, 'result_budget': 9})]
  assert judge.calls == [('complete_json', {'type': 'object'})]


def test_spans_from_both_routes_reach_the_log():
  r = RoutedBackend(Stub('agent'), Stub('judge'))
  assert [s['tool'] for s in r.take_tool_trace()] == ['agent_span', 'judge_span']
  assert r.take_tool_trace() == []


def test_the_engine_builds_a_subscription_only_deploy( tmp_path ):
  pack = Pack(domain='t', goal='g', connector=None, actions={}, analyze=lambda *a, **k: {})
  eng = Engine(cfg(tmp_path, backend='claudeCode', claudeCode={}), pack)
  assert eng.model.label() == 'claudeCode:default'
