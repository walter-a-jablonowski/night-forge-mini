"""`run-loop`: ticks, backoff after failures, the 24 h budget, the wall-clock end — a whole
night driven by a fake clock (scheduler.py)."""
from datetime import datetime, timedelta

import pytest

from night_forge_mini.cli import main
from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.pack import Action, Pack
from night_forge_mini.scheduler import Schedule, Scheduler, next_clock_time, seconds


class Clock:
  """`now` advances only when the scheduler sleeps."""

  def __init__( self, start=datetime(2026, 10, 11, 22, 0) ):
    self.t, self.waits = start, []

  def now( self ):
    return self.t

  def sleep( self, s ):
    self.waits.append(s)
    self.t += timedelta(seconds=s)


class Inbox:
  name = 'stub'

  def __init__( self ):
    self.items = []

  def fetch( self, seen ):
    return [dict(s) for s in self.items if s['id'] not in seen]


def engine( tmp_path, analyze=None, **raw ):
  def proposing( model, *, goal, snippets, history ):
    return {'finding': 'f', 'metric': {'score': 3},
            'actions': [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}]}

  ok = Action(name='improve', risk_level='low', reversible=True,
              run=lambda t, p: {'status': 'ok', 'detail': 'done'})
  cfg = Config(raw={'paths': {'log': 'data/log.jsonl'}, 'allow_list': ['improve'],
                    'recent_runs': 5, **raw}, root=tmp_path)
  return Engine(cfg, Pack(domain='t', goal='g', connector=Inbox(), actions={'improve': ok},
                          analyze=analyze or proposing), fake_llm=True)


def night( eng, clock, **schedule ):
  events = []
  summary = Scheduler(eng, Schedule(**schedule), events.append,
                      now=clock.now, sleep=clock.sleep).run()
  return summary, events


# --- parsing ------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [(90, 90), ('90s', 90), ('15m', 900),
                                             ('1h', 3600), ('2.5m', 150)])
def test_durations( value, expected ):
  assert seconds(value) == expected


def test_a_clock_time_is_the_next_one():
  evening = datetime(2026, 10, 11, 22, 0)
  assert next_clock_time('07:00', evening) == datetime(2026, 10, 12, 7, 0)
  assert next_clock_time('23:30', evening) == datetime(2026, 10, 11, 23, 30)
  with pytest.raises(ValueError):
    next_clock_time('25:00', evening)


# --- the loop ----------------------------------------------------------------------

def test_new_input_is_processed_and_idle_ticks_are_cheap( tmp_path ):
  eng, clock = engine(tmp_path), Clock()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  summary, events = night(eng, clock, interval=600, ticks=3)
  assert [e['kind'] for e in events] == ['ran', 'noop', 'noop']
  assert summary == {'ticks': 3, 'ran': 1, 'failed': 0, 'noop': 2, 'skipped': 0,
                     'stopped': '3 tick(s) done'}
  assert clock.waits == [600, 600]                       # no wait after the last tick


def test_the_night_ends_at_the_wall_clock_time( tmp_path ):
  eng, clock = engine(tmp_path), Clock(datetime(2026, 10, 11, 22, 0))
  summary, events = night(eng, clock, interval=3600, until=datetime(2026, 10, 12, 7, 0))
  assert summary['stopped'] == 'reached 07:00' and summary['ticks'] == 9
  assert clock.t == datetime(2026, 10, 12, 7, 0)         # the last wait is cut to the end


def test_failures_back_off_and_a_success_resets_it( tmp_path ):
  calls = {'n': 0}

  def flaky( model, *, goal, snippets, history ):
    calls['n'] += 1
    if calls['n'] <= 3:
      raise RuntimeError('503 overloaded')
    return {'finding': 'f', 'metric': {}, 'actions': []}

  eng, clock = engine(tmp_path, flaky), Clock()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  summary, events = night(eng, clock, interval=600, ticks=5, max_backoff=3600)
  assert [e['kind'] for e in events] == ['failed', 'failed', 'failed', 'ran', 'noop']
  assert clock.waits == [1200, 2400, 3600, 600]          # doubled, capped, then reset
  errors = [r for r in eng.store.all() if r.type == 'error']
  assert len(errors) == 3                                # every failure is in the log


def test_the_budget_skips_passes_once_spent( tmp_path ):
  eng, clock = engine(tmp_path), Clock()
  for i in range(3):
    eng.pack.connector.items.append({'id': f's{i}', 'text': 'x', 'source': 'x'})
    summary, events = night(eng, clock, interval=60, ticks=1, passes_per_day=2)
  assert [e['kind'] for e in events] == ['skipped']
  assert 'budget: 2 passes in the last 24 h' in events[0]['reason']


def test_a_tick_while_another_pass_holds_the_lock_is_skipped( tmp_path ):
  from night_forge_mini.run_lock import RunLock
  eng, clock = engine(tmp_path), Clock()
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  with RunLock(eng._lock):
    summary, events = night(eng, clock, interval=60, ticks=1)
  assert events[0]['kind'] == 'skipped' and 'another pass' in events[0]['reason']


def test_ctrl_c_ends_the_loop_with_a_summary( tmp_path ):
  eng, clock = engine(tmp_path), Clock()

  def interrupt( s ):
    raise KeyboardInterrupt

  summary = Scheduler(eng, Schedule(interval=60), lambda e: None,
                      now=clock.now, sleep=interrupt).run()
  assert summary['stopped'] == 'interrupted' and summary['ticks'] == 1


# --- the commands ------------------------------------------------------------------

def deploy( tmp_path, monkeypatch ):
  """A minimal deploy dir with a pack, for the real command line."""
  (tmp_path / 'domain_pack').mkdir()
  (tmp_path / 'domain_pack' / '__init__.py').write_text('''
from night_forge_mini.pack import Action, Pack

class Inbox:
    name = 'stub'
    def fetch(self, seen):
        return [{'id': 's1', 'text': 'x', 'source': 'x'}] if 's1' not in seen else []

def analyze(model, *, goal, snippets, history):
    return {'finding': 'f', 'metric': {'score': 3},
            'actions': [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}]}

def build_pack(cfg):
    ok = Action(name='improve', risk_level='low', reversible=True,
                run=lambda t, p: {'status': 'ok', 'detail': 'done'})
    return Pack(domain='t', goal='g', connector=Inbox(), actions={'improve': ok},
                analyze=analyze)
''', encoding='utf-8')
  (tmp_path / 'config.json').write_text(
    '{"paths": {"log": "data/log.jsonl"}, "allow_list": ["improve"], "recent_runs": 5}',
    encoding='utf-8')
  monkeypatch.chdir(tmp_path)
  monkeypatch.syspath_prepend(str(tmp_path))
  import sys
  sys.modules.pop('domain_pack', None)


def test_run_loop_and_the_morning_report( tmp_path, monkeypatch, capsys ):
  deploy(tmp_path, monkeypatch)
  assert main(['--fake-llm', 'run-loop', '--interval', '0s', '--ticks', '2']) == 0
  out = capsys.readouterr().out
  assert 'tick 1' in out and 'tick 2' in out and 'AUTO-RAN ok' in out
  assert 'run-loop ended (2 tick(s) done): 2 tick(s) - 1 ran, 0 failed, 1 idle' in out

  assert main(['--fake-llm', 'report', '--since', '1h']) == 0
  out = capsys.readouterr().out
  assert '1 pass(es), 0 failed · actions 1 ran, 0 failed, 0 held' in out
  assert 'ok  1 ran' in out and 'score=3' in out
