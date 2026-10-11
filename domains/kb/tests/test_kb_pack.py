"""The kb pack is the reference implementation of the `Pack` seam — its job is to prove the
seam works for something other than the website. These tests say that, and nothing more:
the pack's own non-trivial logic, and one offline pass through the real Engine."""
import kb_domain_pack as domain_pack
from kb_domain_pack import analyze as analyze_mod
from kb_domain_pack.actions import KnowledgeBase

from night_forge_mini.config import Config
from night_forge_mini.loop import Engine


def entry( i, title, preview ):
  return {'id': f'e{i}', 'title': title, 'preview': preview}


# --- the context the model sees ---------------------------------------------

def test_findings_are_rendered_with_their_age_and_as_past_state():
  """Long run §5: a bare `RECENT FINDINGS:` list made a solved problem read as current,
  and it was solved a second time. The fix went into both packs; this is the kb half."""
  user = analyze_mod._render_context('goal', [], [], {'findings': ['old', 'new']})
  assert '- 2 runs ago: old' in user and '- 1 run ago: new' in user
  assert 'AS IT WAS' in user and 'NOT the current state' in user


def test_relevant_slice_caps_the_index_by_overlap_and_is_stable_on_ties():
  index = [entry(1, 'Office wifi', 'network name'),
           entry(2, 'VPN setup', 'globalprotect gateway'),
           entry(3, 'Expenses', 'ramp receipts'),
           entry(4, 'Parking', 'garage levels')]
  snippets = [{'text': 'the vpn gateway changed; expenses now in ramp'}]

  got = analyze_mod._relevant_slice(index, snippets, 2)
  assert [e['id'] for e in got] == ['e2', 'e3']                 # overlap 2 each, index order
  assert analyze_mod._relevant_slice(index, snippets, 0) == index   # 0 = no cap
  assert analyze_mod._relevant_slice(index, snippets, 9) == index   # under the cap


def test_a_proposed_edit_is_stamped_with_the_body_it_was_based_on( tmp_path ):
  """The stale-edit guard's own input: without the stamp, an edit approved later would
  silently overwrite whatever changed in between."""
  kb = KnowledgeBase(tmp_path)
  kb.add_entry('vpn', {'title': 'VPN', 'body': 'use eu-west'})
  actions = [{'name': 'edit_entry', 'target': 'vpn'},               # payload missing
             {'name': 'add_entry', 'target': 'new', 'payload': {}}]

  analyze_mod._stamp_edit_base(kb, actions)
  assert actions[0]['payload']['base'] == kb.fingerprint('vpn')
  assert 'base' not in actions[1]['payload']
  analyze_mod._stamp_edit_base(kb, 'not a list')                    # raw model output: no crash

  kb.edit_entry('vpn', {'body': 'use eu-central'})                  # someone edits first
  assert kb.edit_entry('vpn', actions[0]['payload'] | {'body': 'x'})['status'] == 'error'


def source_of( kb, entry_id ):
  return [l for l in kb.read(entry_id).splitlines() if l.startswith('source:')][0]


def test_an_edit_adds_its_snippets_to_the_entrys_sources( tmp_path ):
  """Live 2026-10-11: an update merged into vpn-setup, and `source:` still named only the
  snippets that created the entry."""
  kb = KnowledgeBase(tmp_path)
  kb.add_entry('vpn', {'title': 'VPN', 'body': 'use eu-west', 'source': 'snip-a, snip-b'})
  kb.edit_entry('vpn', {'body': 'use eu-central', 'source': 'snip-c'})
  kb.edit_entry('vpn', {'body': 'and MFA', 'source': ['snip-b', 'snip-d']})   # repeat: once
  assert source_of(kb, 'vpn') == 'source: snip-a, snip-b, snip-c, snip-d'

  kb.edit_entry('vpn', {'body': 'typo fixed'})                     # no source: kept as is
  assert source_of(kb, 'vpn') == 'source: snip-a, snip-b, snip-c, snip-d'


def test_a_list_source_is_written_as_the_frontmatter_list( tmp_path ):
  kb = KnowledgeBase(tmp_path)
  kb.add_entry('wifi', {'title': 'Wifi', 'body': 'b', 'source': ['snip-a', 'snip-b']})
  assert source_of(kb, 'wifi') == 'source: snip-a, snip-b'


def test_the_pack_offers_tools_to_an_agent_backend( tmp_path ):
  """An agent backend with no tools does not fail, it invents — so it refuses the turn.
  The pack must therefore always declare its read tool."""
  kb = KnowledgeBase(tmp_path)
  kb.add_entry('vpn', {'title': 'VPN', 'body': 'use eu-west'})
  tools = analyze_mod.tools_for(kb)
  assert [t.name for t in tools] == ['read_entry'] and all(t.available() for t in tools)
  assert 'use eu-west' in tools[0].run(id='vpn')


# --- the seam contract itself: the core runs this pack ----------------------

def make_engine( tmp_path, snippets: dict[str, str], **extra ) -> Engine:
  inbox = tmp_path / 'data' / 'inbox'
  inbox.mkdir(parents=True)
  for name, text in snippets.items():
    (inbox / name).write_text(text, encoding='utf-8')
  raw = {'provider': 'fake',
         'providers': {'fake': {'base_url': '', 'api_key_env': '', 'model': 'fake'}},
         'paths': {'log': 'data/log.jsonl', 'kb': 'data/kb'},
         'connector': {'source': 'data/inbox'},
         'allow_list': ['add_entry', 'flag_contradiction', 'mark_stale', 'edit_entry'],
         'recent_runs': 5}
  raw.update(extra)
  cfg = Config(raw=raw, root=tmp_path)
  return Engine(cfg, domain_pack.build_pack(cfg), fake_llm=True)


def test_one_offline_pass_through_the_real_engine( tmp_path ):
  engine = make_engine(tmp_path, {'01.md': 'Office WiFi\n\nNetwork Corp-5G.',
                                  '02.md': 'VPN setup\n\nUse eu-west.'})
  out = engine.run_once()

  assert out['status'] == 'ok' and out['captured'] == 2
  assert [r['res']['result']['status'] for r in out['ran']] == ['ok', 'ok']
  assert sorted(p.name for p in (tmp_path / 'data' / 'kb').glob('*.md')) == \
         ['office-wifi.md', 'vpn-setup.md']
  assert engine.run_once()['status'] == 'noop'                      # watermark holds


def test_an_overwrite_is_held_when_git_cannot_undo_it( tmp_path ):
  """edit_entry is allow-listed in the shipped config, but honestly irreversible: without
  git to make it recoverable the gate's hard floor must hold it for a human."""
  engine = make_engine(tmp_path, {'01.md': 'VPN setup\n\nUse eu-west.'})
  engine.run_once()
  (tmp_path / 'data' / 'inbox' / '02.md').write_text('VPN setup\n\nNow eu-central.',
                                                     encoding='utf-8')
  out = engine.run_once()

  assert out['ran'] == []
  assert [a['name'] for a in out['pending']] == ['edit_entry']
  assert 'eu-west' in (tmp_path / 'data' / 'kb' / 'vpn-setup.md').read_text(encoding='utf-8')
