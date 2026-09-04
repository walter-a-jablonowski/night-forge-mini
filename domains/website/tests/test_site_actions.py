"""Site file API: path safety, create-only writes, stale guards, deletes and downloads."""
import pytest

from domain_pack import site as site_mod
from domain_pack.assets import AssetPolicy
from domain_pack.constraints import HardConstraints
from domain_pack.site import Site

HTML = '<!DOCTYPE html><html><head><title>t</title></head><body>x</body></html>'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
OPEN = {'license': 'cc0 1.0', 'creator': 'Jane', 'source': 'https://ex.am/p'}


@pytest.fixture
def site( tmp_path ):
  return Site(tmp_path / 'site')


@pytest.fixture
def downloads( monkeypatch ):
  """Capture add_asset's downloads instead of hitting the network."""
  calls = []

  def fake_fetch( url, **kw ):
    calls.append({'url': url, 'kw': kw})
    return PNG

  monkeypatch.setattr(site_mod, 'fetch_binary', fake_fetch)
  return calls


def test_safe_path_refuses_escapes_and_bad_extensions( site ):
  for bad in ('../evil.html', 'a/../../evil.html',
              'C:/evil.html', 'x:alternate.html', 'page.exe', 'page', ''):
    assert site.safe_path(bad) is None, bad
  assert site.safe_path('index.html') is not None
  assert site.safe_path('sub/dir/page.php') is not None
  assert site.safe_path('style.css') is not None
  # a leading slash is site-ROOT-relative (models often emit "/index.html"), never absolute
  assert site.safe_path('/etc/passwd.html') == site.dir / 'etc' / 'passwd.html'


def test_create_page_is_create_only( site ):
  assert site.create_page('index.html', {'content': HTML})['status'] == 'ok'
  res = site.create_page('index.html', {'content': 'other'})
  assert res['status'] == 'error'
  assert 'edit_content' in res['detail']
  assert site.read('index.html') == HTML                 # first content untouched


def test_create_page_makes_subfolders_and_refuses_empty( site ):
  assert site.create_page('meals/bowls.html', {'content': HTML})['status'] == 'ok'
  assert site.pages() == ['meals/bowls.html']
  assert site.create_page('empty.html', {'content': '  '})['status'] == 'error'


def test_edit_content_requires_existing_file( site ):
  res = site.edit_content('missing.html', {'content': HTML})
  assert res['status'] == 'error'
  assert 'create_page' in res['detail']


def test_edit_content_stale_base_refused( site ):
  site.create_page('index.html', {'content': HTML})
  base = site.fingerprint('index.html')
  site.edit_content('index.html', {'content': HTML + '<!-- intervening -->'})
  res = site.edit_content('index.html', {'content': 'new', 'base': base})
  assert res['status'] == 'error'
  assert 'changed since proposed' in res['detail']


def test_edit_content_with_current_base_succeeds( site ):
  site.create_page('index.html', {'content': HTML})
  res = site.edit_content('index.html', {'content': HTML + '<p>more</p>',
                                         'base': site.fingerprint('index.html')})
  assert res['status'] == 'ok'
  assert 'more' in site.read('index.html')


def test_site_map_and_files_skip_git_dir( site ):
  site.create_page('index.html', {'content': HTML})
  (site.dir / '.git').mkdir()
  (site.dir / '.git' / 'x.html').write_text('nope', encoding='utf-8')
  assert [e['path'] for e in site.site_map()] == ['index.html']
  assert site.site_map()[0]['title'] == 't'


# --- change_design ----------------------------------------------------------

def test_change_design_writes_css_and_refuses_other_targets( site ):
  res = site.change_design('style.css', {'content': 'body { color: gold; }'})
  assert res['status'] == 'ok' and 'created' in res['detail']
  res = site.change_design('style.css', {'content': 'body { color: orange; }'})
  assert res['status'] == 'ok' and 'restyled' in res['detail']    # create-OR-overwrite
  for bad in ('index.html', 'notes.txt', '../x.css'):
    assert site.change_design(bad, {'content': 'x{}'})['status'] == 'error', bad


def test_change_design_stale_base_refused( site ):
  site.change_design('style.css', {'content': 'a{}'})
  base = site.fingerprint('style.css')
  site.change_design('style.css', {'content': 'b{}'})
  res = site.change_design('style.css', {'content': 'c{}', 'base': base})
  assert res['status'] == 'error' and 'changed since proposed' in res['detail']


def test_change_design_refuses_forbidden_colors( tmp_path ):
  site = Site(tmp_path / 'site', hard=HardConstraints(forbidden_colors=['blue']))
  res = site.change_design('style.css', {'content': 'a { color: blue; }'})
  assert res['status'] == 'error' and 'refused' in res['detail']
  assert not (site.dir / 'style.css').exists()                    # nothing written


def test_page_writes_refuse_hotlinked_images( site ):
  res = site.create_page('p.html', {'content': '<img src="https://ex.am/x.jpg">'})
  assert res['status'] == 'error' and 'add_asset' in res['detail']


# --- remove_page ------------------------------------------------------------

def test_remove_page_deletes_and_refuses_the_home_page( site ):
  site.create_page('index.html', {'content': HTML})
  site.create_page('pages/old.html', {'content': HTML})
  assert site.remove_page('pages/old.html', {})['status'] == 'ok'
  assert site.pages() == ['index.html']

  res = site.remove_page('index.html', {})
  assert res['status'] == 'error' and 'home page' in res['detail']
  assert site.exists('index.html')


def test_remove_page_refuses_stylesheets_and_missing_files( site ):
  site.change_design('style.css', {'content': 'a{}'})
  assert site.remove_page('style.css', {})['status'] == 'error'   # pages only
  assert site.exists('style.css')
  assert site.remove_page('pages/ghost.html', {})['status'] == 'error'


# --- add_asset --------------------------------------------------------------

def test_add_asset_downloads_and_writes_the_attribution_sidecar( site, downloads ):
  res = site.add_asset('assets/veg.png', {'url': 'https://any.host/v.png', **OPEN})
  assert res['status'] == 'ok'
  assert (site.dir / 'assets/veg.png').read_bytes() == PNG
  sidecar = (site.dir / 'assets/veg.png.license.txt').read_text(encoding='utf-8')
  assert 'https://any.host/v.png' in sidecar and 'cc0 1.0' in sidecar and 'Jane' in sidecar
  assert site.assets() == ['assets/veg.png']
  assert downloads[0]['kw']['max_bytes'] == site.asset_policy.max_bytes


def test_add_asset_is_create_only_and_confined_to_the_assets_dir( site, downloads ):
  site.add_asset('assets/veg.png', {'url': 'https://any.host/v.png', **OPEN})
  res = site.add_asset('assets/veg.png', {'url': 'https://any.host/other.png', **OPEN})
  assert res['status'] == 'error' and 'create-only' in res['detail']
  res = site.add_asset('veg.png', {'url': 'https://any.host/v.png', **OPEN})
  assert res['status'] == 'error' and 'assets/' in res['detail']
  res = site.add_asset('assets/page.html', {'url': 'https://any.host/v.png', **OPEN})
  assert res['status'] == 'error'                                 # not an asset extension
  assert len(downloads) == 1                                      # refusals never fetch


def test_add_asset_refuses_an_unlicensed_source( site, downloads ):
  res = site.add_asset('assets/x.png', {'url': 'https://any.host/x.png'})
  assert res['status'] == 'error' and 'refused' in res['detail']
  assert downloads == []
  assert not (site.dir / 'assets/x.png').exists()


def test_add_asset_accepts_an_operator_host_without_a_license( tmp_path, downloads ):
  site = Site(tmp_path / 'site', asset_policy=AssetPolicy(allowed_hosts=['brand.example']))
  res = site.add_asset('assets/logo.svg', {'url': 'https://brand.example/logo.svg'})
  assert res['status'] == 'ok'


def test_add_asset_reports_a_failed_download( site, monkeypatch ):
  def boom( url, **kw ):
    raise ValueError('body exceeds max_bytes')

  monkeypatch.setattr(site_mod, 'fetch_binary', boom)
  res = site.add_asset('assets/big.png', {'url': 'https://any.host/big.png', **OPEN})
  assert res['status'] == 'error' and 'download failed' in res['detail']
  assert not (site.dir / 'assets/big.png').exists()


def test_every_write_enforces_the_css_constraint_on_a_stylesheet( tmp_path ):
  """A hard constraint a model can route around by picking another action is a soft one:
  edit_content on a .css used to skip check_css entirely (found in run-9d177565)."""
  site = Site(tmp_path / 'site', hard=HardConstraints(forbidden_colors=['blue']))
  css = tmp_path / 'site' / 'style.css'
  css.parent.mkdir(parents=True, exist_ok=True)
  css.write_text('body { color: white; }', encoding='utf-8')
  bad = 'body { color: blue; }'

  for name, target in (('create_page', 'new.css'), ('edit_content', 'style.css'),
                       ('change_design', 'style.css')):
    res = getattr(site, name)(target, {'content': bad})
    assert res['status'] == 'error', f'{name} wrote forbidden CSS'
    assert 'forbidden color' in res['detail']

  assert css.read_text(encoding='utf-8') == 'body { color: white; }'
  assert not (tmp_path / 'site' / 'new.css').exists()
