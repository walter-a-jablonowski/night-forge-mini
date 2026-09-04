"""End-to-end: the blank Engine running the website pack offline (--fake-llm),
with and without git-backed autonomy for the irreversible writes."""
import json
import subprocess

import pytest

from night_forge_mini.config import Config
from night_forge_mini.loop import Engine

import domain_pack
from domain_pack import connector as conn_mod
from domain_pack import site as site_mod

SEED = ('<!DOCTYPE html><html><head><title>New Site</title></head>'
        '<body><main><h1>New Site</h1></main></body></html>')
SEED_CSS = 'body { background: #111; color: #eee; }'   # pages the pack writes link to it


def make_cfg( tmp_path, git_enabled: bool, **extra ) -> Config:
  raw = {
    'provider': 'fake',
    'providers': {'fake': {'base_url': '', 'api_key_env': '', 'model': 'fake'}},
    'paths': {'log': 'data/log.jsonl', 'site': 'data/site'},
    'site_goal': 'a simple healthy nutrition site',
    'connector': {'mode': 'pages', 'pages': ['https://source.example/']},
    'metrics': ['pages', 'broken_links', 'seo_basics', 'goal_coverage'],
    'allow_list': ['create_page', 'add_asset', 'edit_content', 'change_design', 'remove_page'],
    'recent_runs': 5,
  }
  raw.update(extra)
  if git_enabled:
    raw['git'] = {'enabled': True, 'repo_dir': 'data/site',
                  'granularity': 'per_action', 'remote': '', 'branch': 'main'}
  return Config(raw=raw, root=tmp_path)


def make_engine( tmp_path, monkeypatch, *, git_enabled: bool, page_text: str,
                 **extra ) -> Engine:
  site_dir = tmp_path / 'data' / 'site'
  site_dir.mkdir(parents=True, exist_ok=True)
  (site_dir / 'index.html').write_text(SEED, encoding='utf-8')
  (site_dir / 'style.css').write_text(SEED_CSS, encoding='utf-8')   # the shipped seed has
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: page_text)
  cfg = make_cfg(tmp_path, git_enabled, **extra)
  if git_enabled:
    git(site_dir, 'init')
    git(site_dir, 'config', 'user.email', 'test@test')
    git(site_dir, 'config', 'user.name', 'test')
    git(site_dir, 'add', '-A')
    git(site_dir, 'commit', '-m', 'seed')
  return Engine(cfg, domain_pack.build_pack(cfg), fake_llm=True)


def git( cwd, *args ):
  res = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True)
  assert res.returncode == 0, res.stderr
  return res.stdout


def with_proposal( eng, *actions ):
  """Drive the Engine's gate with a fixed proposal. The fake-LLM analyze only exercises
  create_page/edit_content, so the phase-2 actions get their gate coverage here — the
  path under test is the CORE's (sanitize -> gate -> run -> commit), not the model's."""
  def analyze( model, *, goal, snippets, history ):
    return {'finding': 'fixed proposal', 'actions': [dict(a) for a in actions],
            'metric': {}, 'model': 'stub'}

  eng.pack.analyze = analyze
  return eng


def test_run_creates_page_and_measures_metrics( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False,
                    page_text='Healthy Bowls\nput in a bowl, heat up, ready')
  res = eng.run_once()
  assert res['status'] == 'ok'
  assert res['captured'] == 1
  # fake analyze proposes create_page (reversible + allow-listed) -> auto-run even without git
  assert [r['action']['name'] for r in res['ran']] == ['create_page']
  assert res['pending'] == []
  assert (tmp_path / 'data/site/pages/healthy-bowls.html').is_file()
  assert res['metric']['pages'] == 1            # measured at analyze time, BEFORE acting
  assert res['metric']['goal_coverage'] == 5.0  # judge metric: deterministic in fake mode
  assert res['metric']['incoming_new'] == 1


def test_unchanged_source_is_noop( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='same text')
  assert eng.run_once()['status'] == 'ok'
  assert eng.run_once()['status'] == 'noop'     # url#hash unchanged -> watermark holds


def test_edit_holds_without_git_and_runs_on_approval( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Healthy Bowls\nv1')
  eng.run_once()                                # creates pages/healthy-bowls.html
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  res = eng.run_once()
  # page exists now -> fake analyze proposes edit_content; no git -> irreversible -> HELD
  assert res['ran'] == []
  assert [a['name'] for a in res['pending']] == ['edit_content']
  page = tmp_path / 'data/site/pages/healthy-bowls.html'
  assert 'v1' in page.read_text(encoding='utf-8')

  approved = eng.approve(res['pending'][0]['action_id'])
  assert approved['res']['result']['status'] == 'ok'
  assert 'v2' in page.read_text(encoding='utf-8')


def test_edit_autoruns_with_git_and_is_committed( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=True, page_text='Healthy Bowls\nv1')
  r1 = eng.run_once()
  assert [r['action']['name'] for r in r1['ran']] == ['create_page']
  assert [g['status'] for g in r1['git']] == ['ok']     # per-action commit

  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  r2 = eng.run_once()
  # git-backed autonomy: irreversible edit_content auto-runs because git supplies the undo
  assert [r['action']['name'] for r in r2['ran']] == ['edit_content']
  assert r2['pending'] == []
  page = tmp_path / 'data/site/pages/healthy-bowls.html'
  assert 'v2' in page.read_text(encoding='utf-8')

  log = git(tmp_path / 'data/site', 'log', '--format=%s')
  assert 'edit_content' in log and 'create_page' in log and 'seed' in log


def test_change_design_autoruns_with_git_and_is_committed( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=True, page_text='Bowls')
  with_proposal(eng, {'name': 'change_design', 'target': 'style.css',
                      'rationale': 'warm accents', 'payload': {'content': ':root{--a:gold}'}})
  res = eng.run_once()
  assert [r['action']['name'] for r in res['ran']] == ['change_design']
  assert (tmp_path / 'data/site/style.css').read_text(encoding='utf-8') == ':root{--a:gold}'
  assert 'change_design' in git(tmp_path / 'data/site', 'log', '--format=%s')


def test_remove_page_holds_without_git_and_autoruns_with_it( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Bowls')
  (tmp_path / 'data/site/old.html').write_text(SEED, encoding='utf-8')
  with_proposal(eng, {'name': 'remove_page', 'target': 'old.html',
                      'rationale': 'superseded', 'payload': {}})
  res = eng.run_once()
  assert [a['name'] for a in res['pending']] == ['remove_page']   # deletion is irreversible
  assert (tmp_path / 'data/site/old.html').is_file()

  eng2 = make_engine(tmp_path / 'g', monkeypatch, git_enabled=True, page_text='Bowls')
  (tmp_path / 'g/data/site/old.html').write_text(SEED, encoding='utf-8')
  git(tmp_path / 'g/data/site', 'add', '-A')
  git(tmp_path / 'g/data/site', 'commit', '-m', 'add old')
  with_proposal(eng2, {'name': 'remove_page', 'target': 'old.html',
                       'rationale': 'superseded', 'payload': {}})
  res2 = eng2.run_once()
  assert [r['action']['name'] for r in res2['ran']] == ['remove_page']
  assert not (tmp_path / 'g/data/site/old.html').exists()


def test_add_asset_autoruns_without_git_and_records_provenance( tmp_path, monkeypatch ):
  monkeypatch.setattr(site_mod, 'fetch_binary', lambda url, **kw: b'\x89PNG\r\n\x1a\n')
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Bowls')
  with_proposal(eng, {'name': 'add_asset', 'target': 'assets/veg.png',
                      'rationale': 'illustrate the meal page',
                      'payload': {'url': 'https://any.host/v.png', 'license': 'cc0 1.0',
                                  'creator': 'Jane', 'source': 'https://any.host/p'}})
  res = eng.run_once()
  # create-only -> honestly reversible -> auto-runs even with no git configured
  assert [r['action']['name'] for r in res['ran']] == ['add_asset']
  assert (tmp_path / 'data/site/assets/veg.png').is_file()
  assert 'cc0 1.0' in (tmp_path / 'data/site/assets/veg.png.license.txt').read_text(
    encoding='utf-8')


def test_a_refused_write_is_logged_as_a_failed_outcome( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=True, page_text='Bowls',
                    hard_constraints={'forbidden_colors': ['blue']})
  with_proposal(eng, {'name': 'change_design', 'target': 'style.css',
                      'rationale': 'restyle', 'payload': {'content': 'a{color:blue}'}})
  res = eng.run_once()
  # the hard constraint refuses INSIDE the action: it was auto-run, it failed cleanly,
  # nothing was written and the loop survived
  outcome = res['ran'][0]['res']['result']
  assert outcome['status'] == 'error' and 'forbidden color' in outcome['detail']
  assert (tmp_path / 'data/site/style.css').read_text(encoding='utf-8') == SEED_CSS
  assert res['git'] == []                              # a failed action is never committed
  # ...and the refusal comes back to the model on the next run
  failures = eng.store.recent_failures(5)
  assert failures and failures[0]['name'] == 'change_design'


def test_stamped_base_is_in_the_proposal_log( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Healthy Bowls\nv1')
  eng.run_once()
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  res = eng.run_once()
  # stale-edit guard: the held edit carries the fingerprint of what it was based on
  assert res['pending'][0]['payload'].get('base')
  records = [json.loads(line) for line in
             (tmp_path / 'data/log.jsonl').read_text(encoding='utf-8').splitlines()]
  assert any(r['type'] == 'proposal' for r in records)


def test_pending_work_reports_broken_internal_links( tmp_path, monkeypatch ):
  """The site's own unfinished business must be able to trigger a pass: run-9d177565 left
  index.html linking to two pages it never created, and every later run was a noop."""
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='fresh')
  site_dir = tmp_path / 'data' / 'site'

  assert eng.pack.pending_work() is None                    # seed links to nothing missing

  (site_dir / 'index.html').write_text(
    '<html><head><title>t</title></head><body><a href="meals.html">m</a></body></html>',
    encoding='utf-8')
  reason = eng.pack.pending_work()
  assert reason and '1' in reason

  (site_dir / 'meals.html').write_text('<html><head><title>m</title></head></html>',
                                       encoding='utf-8')
  assert eng.pack.pending_work() is None                    # target exists -> nothing pending
