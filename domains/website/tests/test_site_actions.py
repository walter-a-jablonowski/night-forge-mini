"""Site file API: path safety, create-only create_page, stale-guarded edit_content."""
import pytest

from domain_pack.site import Site

HTML = '<!DOCTYPE html><html><head><title>t</title></head><body>x</body></html>'


@pytest.fixture
def site( tmp_path ):
  return Site(tmp_path / 'site')


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
