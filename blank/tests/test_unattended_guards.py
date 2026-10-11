"""The two guards unattended running needs: one writer per deploy (run_lock.py), and a log
record for a pass that failed (tasks/backlog/run-lock.md, failed-pass-record.md)."""
import os
import signal
import subprocess
import sys
import time

import pytest

from night_forge_mini.cli import main
from night_forge_mini.config import Config
from night_forge_mini.loop import BUSY, Engine
from night_forge_mini.pack import Action, Pack
from night_forge_mini.run_lock import RunLock


class Inbox:
  name = 'stub'

  def __init__( self, fail=False ):
    self.items, self.fail = [], fail

  def fetch( self, seen ):
    if self.fail:
      raise ConnectionError('source unreachable')
    return [dict(s) for s in self.items if s['id'] not in seen]


class Metered:
  """A backend that reports usage, standing in for a real one that then fails."""
  fake = False

  def __init__( self ):
    self.usage, self.trace = {}, []

  def take_tool_trace( self ):
    t, self.trace = self.trace, []
    return t

  def take_usage( self ):
    u, self.usage = self.usage, {}
    return u

  def label( self ):
    return 'metered'


def engine( tmp_path, analyze, connector=None, **raw ):
  ok = Action(name='improve', risk_level='low', reversible=True,
              run=lambda t, p: {'status': 'ok', 'detail': 'done'})
  cfg = Config(raw={'paths': {'log': 'data/log.jsonl'}, 'allow_list': ['improve'],
                    'recent_runs': 5, **raw}, root=tmp_path)
  pack = Pack(domain='t', goal='g', connector=connector or Inbox(),
              actions={'improve': ok}, analyze=analyze)
  return Engine(cfg, pack, fake_llm=True)


def proposing( model, *, goal, snippets, history ):
  return {'finding': 'f', 'metric': {'score': 3},
          'actions': [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}]}


# --- the run lock --------------------------------------------------------------

def test_a_lock_is_exclusive_and_released( tmp_path ):
  path = tmp_path / 'log.jsonl.lock'
  with RunLock(path) as first:
    with RunLock(path) as second:
      assert first is True and second is False
  with RunLock(path) as again:
    assert again is True


HOLDER = '''
import sys
sys.path.insert(0, sys.argv[2])
from night_forge_mini.run_lock import RunLock
import os
with RunLock(sys.argv[1]) as held:
    print(('held' if held else 'missed'), os.getpid(), flush=True)
    sys.stdin.read()          # hold until the test closes our stdin
'''


def test_a_pass_skips_while_another_process_holds_the_lock( tmp_path ):
  """The real case: a scheduled pass in one process, `run-once` typed in another."""
  eng = engine(tmp_path, proposing)
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  import night_forge_mini
  pkg_root = str(__import__('pathlib').Path(night_forge_mini.__file__).parent.parent)
  holder = subprocess.Popen([sys.executable, '-c', HOLDER, str(eng._lock), pkg_root],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
  try:
    assert holder.stdout.readline().split()[0] == 'held'
    r = eng.run_once()
    assert r['status'] == 'noop' and r['busy'] and r['reason'] == BUSY
    assert eng.store.all() == []                         # nothing written, input not consumed
  finally:
    holder.stdin.close()
    holder.wait(timeout=10)
  assert eng.run_once()['captured'] == 1                 # the holder is gone: it runs


def test_a_lock_does_not_outlive_a_killed_holder( tmp_path ):
  """A pid file would: the machine slept during a live pass, and the process died."""
  import night_forge_mini
  pkg_root = str(__import__('pathlib').Path(night_forge_mini.__file__).parent.parent)
  path = tmp_path / 'log.jsonl.lock'
  holder = subprocess.Popen([sys.executable, '-c', HOLDER, str(path), pkg_root],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
  state, pid = holder.stdout.readline().split()
  assert state == 'held'
  # the interpreter itself, by pid: on Windows a venv's python.exe is a launcher, and
  # killing it leaves the real interpreter - and its lock - alive
  os.kill(int(pid), signal.SIGTERM)
  holder.wait(timeout=10)
  for _ in range(50):                  # Windows releases a dead holder's lock shortly after
    with RunLock(path) as held:
      if held:
        break
    time.sleep(0.1)
  assert held is True


def test_an_approve_during_a_pass_is_refused_not_interleaved( tmp_path ):
  eng = engine(tmp_path, proposing, allow_list=[])          # hold everything
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  action_id = eng.run_once()['pending'][0]['action_id']
  with RunLock(eng._lock):
    assert eng.approve(action_id) == {'status': 'error', 'reason': BUSY}
  assert eng.approve(action_id)['status'] == 'ok'


# --- a failed pass leaves a record -------------------------------------------------

def failing( model, *, goal, snippets, history ):
  model.usage = {'calls': 3, 'input_tokens': 9000}
  model.trace = [{'tool': 'read', 'args': {}, 'status': 'ok', 'chars': 10}]
  raise RuntimeError('429 quota exceeded')


def test_a_failed_pass_is_recorded_with_its_stage_reason_and_cost( tmp_path ):
  eng = engine(tmp_path, failing)
  eng.model = Metered()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  with pytest.raises(RuntimeError, match='429'):         # still propagates: exit code 1
    eng.run_once()
  error = [r for r in eng.store.all() if r.type == 'error'][0]
  assert error.payload['stage'] == 'analyze'
  assert error.payload['error'] == 'RuntimeError: 429 quota exceeded'
  assert error.payload['usage'] == {'calls': 3, 'input_tokens': 9000}
  spans = [r for r in eng.store.all() if r.type == 'tool_call']
  assert spans[0].parent_id == error.id                  # the reads it had made, too


def test_a_connector_that_cannot_fetch_is_recorded_too( tmp_path ):
  eng = engine(tmp_path, proposing, connector=Inbox(fail=True))
  with pytest.raises(ConnectionError):
    eng.run_once()
  [error] = eng.store.all()
  assert error.type == 'error' and error.payload['stage'] == 'capture'


def test_the_failed_input_is_fetched_again( tmp_path ):
  eng = engine(tmp_path, failing)
  eng.model = Metered()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  with pytest.raises(RuntimeError):
    eng.run_once()
  eng.pack.analyze = proposing
  assert eng.run_once()['captured'] == 1


def test_a_failed_pass_does_not_block_the_next_metric_driven_one( tmp_path ):
  """Anti-spin skips failed runs: one transient 429 must not stop an unattended loop
  until new input arrives."""
  calls = {'n': 0}

  def flaky( model, *, goal, snippets, history ):
    calls['n'] += 1
    if calls['n'] == 2:
      raise RuntimeError('503 overloaded')
    return proposing(model, goal=goal, snippets=snippets, history=history)

  eng = engine(tmp_path, flaky, metric_targets={'score': 8})
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  eng.run_once()                                         # input-driven, score 3
  with pytest.raises(RuntimeError):
    eng.run_once()                                       # metric-driven, fails
  assert eng.run_once()['status'] == 'ok'                # metric-driven again: not blocked


def test_trace_shows_the_failure( tmp_path, capsys ):
  eng = engine(tmp_path, failing)
  eng.model = Metered()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  with pytest.raises(RuntimeError):
    eng.run_once()
  from night_forge_mini.cli import _trace
  _trace(eng, eng.store.all()[0].run_id)
  out = capsys.readouterr().out
  assert 'FAILED in analyze: RuntimeError: 429 quota exceeded' in out
  assert 'usage: 3 call(s) · 9.0k in' in out
