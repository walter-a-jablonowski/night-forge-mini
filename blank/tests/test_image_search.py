"""image_search built-in: Openverse, keyless, license-filtered, no network in tests."""
import pytest

from night_forge_mini.tools import registry, image_search as ims

RESP = {'results': [
  {'title': 'Fresh vegetables', 'url': 'https://cdn.ex.am/veg.jpg',
   'creator': 'Jane Doe', 'license': 'by-sa', 'license_version': '4.0',
   'foreign_landing_url': 'https://ex.am/photos/veg',
   'attribution': '"Fresh vegetables" by Jane Doe is licensed\n under CC BY-SA 4.0.'},
]}


def capture_get( monkeypatch, response ):
  calls = []

  def fake_get( url, timeout ):
    calls.append(url)
    return response

  monkeypatch.setattr(ims, '_get_json', fake_get)
  return calls


def test_registered_and_always_available():
  tool = registry.get('image_search')
  assert tool is not None
  assert tool.params['required'] == ['query']
  assert tool.available() is True                       # keyless -> never disabled


def test_results_carry_url_license_and_attribution( monkeypatch ):
  capture_get(monkeypatch, RESP)
  out = ims.image_search('vegetables')
  assert 'https://cdn.ex.am/veg.jpg' in out             # the direct download url
  assert 'https://ex.am/photos/veg' in out              # the landing page to credit
  assert 'by-sa 4.0' in out and 'Jane Doe' in out
  assert 'licensed under CC BY-SA 4.0.' in out          # newlines collapsed


def test_request_is_filtered_to_reusable_licenses( monkeypatch ):
  calls = capture_get(monkeypatch, RESP)
  ims.image_search('vegetables', max_results=99)
  assert 'license_type=commercial%2Cmodification' in calls[0]
  assert 'page_size=10' in calls[0]                     # clamped to 1..10


def test_attribution_is_built_when_the_api_omits_it( monkeypatch ):
  capture_get(monkeypatch, {'results': [{'title': 'Oats', 'creator': 'Bob',
                                         'license': 'cc0', 'license_version': '1.0',
                                         'url': 'https://cdn.ex.am/o.png'}]})
  out = ims.image_search('oats')
  assert '"Oats" by Bob is licensed under CC0 1.0.' in out


def test_no_results_is_a_readable_message( monkeypatch ):
  capture_get(monkeypatch, {'results': []})
  assert 'no openly-licensed images' in ims.image_search('unobtainium')


def test_open_licenses_permit_commercial_use_and_modification():
  # the set add_asset trusts; nc/nd variants must never leak into it
  assert ims.OPEN_LICENSES == {'by', 'by-sa', 'cc0', 'pdm'}
