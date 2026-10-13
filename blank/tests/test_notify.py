"""The push half of unattended use: the operator's command runs when a human is needed —
actions held, a failure streak, the budget spent — once per condition, never on every tick
(notify.py)."""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

from night_forge_mini.cli import main
from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.notify import Notifier
from night_forge_mini.pack import Action, Pack
from night_forge_mini.scheduler import Schedule, Scheduler


class Runner:
  """Stands in for subprocess.run and remembers what it was asked to send."""

  def __init__( self, returncode=0, stderr='', raises=None ):
    self.calls, self.returncode, self.stderr, self.raises = [], returncode, stderr, raises

  def __call__( self, command, **kw ):
    if self.raises:
      raise self.raises
    self.calls.append(kw['env'])
    return SimpleNamespace(returncode=self.returncode, stdout='', stderr=self.stderr)

  def events( self ):
    return [env['NFM_EVENT'] for env in self.calls]


def held_pass( *names ):
  return {'kind': 'ran', 'result': {'status': 'ok', 'pending': [{'name': n} for n in names]}}


FAILED = {'kind': 'failed', 'error': 'RateLimitError: 429'}
IDLE = {'kind': 'noop', 'result': {'status': 'noop'}, 'reason': 'no new snippets'}
CLEAN = {'kind': 'ran', 'result': {'status': 'ok', 'pending': []}}
BUDGET = {'kind': 'skipped', 'reason': 'budget: 16 passes in the last 24 h (limit 16)'}
BUSY = {'kind': 'skipped', 'result': {'busy': True}, 'reason': 'another pass is running'}


def observe( notifier, *events ):
  return [notifier.observe(dict(e)) for e in events]


# --- when it tells --------------------------------------------------------------

def test_a_pass_that_leaves_actions_held_is_told_with_what_is_held():
  run = Runner()
  line, = observe(Notifier('cmd', deploy='kb', run=run), held_pass('edit_entry', 'add_entry'))
  env = run.calls[0]
  assert env['NFM_EVENT'] == 'held' and env['NFM_DEPLOY'] == 'kb'
  assert env['NFM_MESSAGE'] == 'kb: 2 action(s) held for approval (add_entry, edit_entry) - run `inbox`'
  assert line == 'notified (held): ' + env['NFM_MESSAGE']


def test_quiet_ticks_tell_nothing():
  run = Runner()
  assert observe(Notifier('cmd', run=run), IDLE, CLEAN, BUSY) == ['', '', '']
  assert run.calls == []


def test_a_failure_streak_is_told_once_and_again_only_after_a_success():
  run = Runner()
  observe(Notifier('cmd', after_failures=3, run=run),
          FAILED, FAILED, FAILED, FAILED, FAILED, CLEAN, FAILED, FAILED, FAILED)
  assert run.events() == ['failing', 'failing']
  assert '3 pass(es) failed in a row - last: RateLimitError: 429' in run.calls[0]['NFM_MESSAGE']


def test_a_spent_budget_is_told_once_per_stretch():
  run = Runner()
  observe(Notifier('cmd', run=run), BUDGET, BUDGET, BUDGET, IDLE, BUDGET)
  assert run.events() == ['budget', 'budget']


def test_a_broken_notifier_is_reported_not_raised():
  failing = Notifier('cmd', run=Runner(returncode=2, stderr='no such command'))
  assert observe(failing, held_pass('x')) == ['notify failed (held): exit 2 no such command']
  hung = Notifier('cmd', run=Runner(raises=subprocess.TimeoutExpired('cmd', 30)))
  assert observe(hung, held_pass('x'))[0].startswith('notify failed (held): TimeoutExpired')


def test_it_is_off_without_a_command( tmp_path ):
  assert Notifier.from_config(Config(raw={}, root=tmp_path)) is None
  assert Notifier.from_config(Config(raw={'notify': {'command': ' '}}, root=tmp_path)) is None
  n = Notifier.from_config(Config(raw={'notify': {'command': 'x', 'after_failures': 2}},
                                  root=tmp_path / 'website'))
  assert n.deploy == 'website' and n.after_failures == 2


# --- the real shell ---------------------------------------------------------------

def test_the_message_reaches_the_command_as_data_not_as_shell_syntax( tmp_path, monkeypatch ):
  """Model text and error text end up in the message: a quote or an `&` in it must arrive
  verbatim, not run as shell syntax."""
  monkeypatch.chdir(tmp_path)
  command = (f'"{sys.executable}" -c "import os; '
             f"open('msg.txt', 'w').write(os.environ['NFM_MESSAGE'])\"")
  tricky = {'kind': 'failed', 'error': 'say "hi" & echo pwned > owned.txt'}
  line, = observe(Notifier(command, deploy='kb', after_failures=1), tricky)
  assert line.startswith('notified (failing)')
  assert 'say "hi" & echo pwned > owned.txt' in (tmp_path / 'msg.txt').read_text()
  assert not (tmp_path / 'owned.txt').exists()


# --- inside the loop ----------------------------------------------------------------

class Inbox:
  name = 'stub'

  def __init__( self ):
    self.items = []

  def fetch( self, seen ):
    return [dict(s) for s in self.items if s['id'] not in seen]


def test_the_loop_tells_a_held_pass_once( tmp_path ):
  def proposing( model, *, goal, snippets, history ):
    return {'finding': 'f', 'metric': {},
            'actions': [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}]}

  ok = Action(name='improve', risk_level='low', reversible=True,
              run=lambda t, p: {'status': 'ok', 'detail': 'done'})
  cfg = Config(raw={'paths': {'log': 'data/log.jsonl'}, 'allow_list': [], 'recent_runs': 5},
               root=tmp_path)
  eng = Engine(cfg, Pack(domain='t', goal='g', connector=Inbox(), actions={'improve': ok},
                         analyze=proposing), fake_llm=True)
  eng.pack.connector.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  clock = [datetime(2026, 10, 13, 22, 0)]
  run, events = Runner(), []

  def sleep( s ):
    clock[0] += timedelta(seconds=s)

  Scheduler(eng, Schedule(interval=60, ticks=3), events.append, now=lambda: clock[0],
            sleep=sleep, notifier=Notifier('cmd', deploy='t', run=run)).run()
  assert [e['kind'] for e in events] == ['ran', 'noop', 'noop']
  assert run.events() == ['held']                  # still held later, but already told
  assert events[0]['notify'].startswith('notified (held): t: 1 action(s) held')


def test_run_loop_runs_the_configured_command( tmp_path, monkeypatch, capsys ):
  (tmp_path / 'domain_pack').mkdir()
  (tmp_path / 'domain_pack' / '__init__.py').write_text('''
from night_forge_mini.pack import Action, Pack

class Inbox:
    name = 'stub'
    def fetch(self, seen):
        return [{'id': 's1', 'text': 'x', 'source': 'x'}] if 's1' not in seen else []

def analyze(model, *, goal, snippets, history):
    return {'finding': 'f', 'metric': {},
            'actions': [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}]}

def build_pack(cfg):
    ok = Action(name='improve', risk_level='low', reversible=True,
                run=lambda t, p: {'status': 'ok', 'detail': 'done'})
    return Pack(domain='t', goal='g', connector=Inbox(), actions={'improve': ok},
                analyze=analyze)
''', encoding='utf-8')
  command = (f'"{sys.executable}" -c "import os; '
             f"open('told.txt', 'w').write(os.environ['NFM_EVENT'])\"")
  (tmp_path / 'config.json').write_text(json.dumps(
    {'paths': {'log': 'data/log.jsonl'}, 'allow_list': [], 'recent_runs': 5,
     'notify': {'command': command}}), encoding='utf-8')
  monkeypatch.chdir(tmp_path)
  monkeypatch.syspath_prepend(str(tmp_path))
  sys.modules.pop('domain_pack', None)

  assert main(['--fake-llm', 'run-loop', '--interval', '0s', '--ticks', '1']) == 0
  out = capsys.readouterr().out
  assert 'notify: ' in out and 'PENDING' in out and 'notified (held)' in out
  assert (tmp_path / 'told.txt').read_text() == 'held'
