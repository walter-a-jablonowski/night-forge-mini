"""web_search built-in: one tool, Tavily/Exa behind it, keyed via .env, no network in tests."""
import pytest

from night_forge_mini.tools import registry, web_search as ws


@pytest.fixture(autouse=True)
def no_keys( monkeypatch ):
  """Start every test with a clean search-key environment."""
  for var in ('TAVILY_API_KEY', 'EXA_API_KEY', 'WEB_SEARCH_PROVIDER'):
    monkeypatch.delenv(var, raising=False)


def capture_post( monkeypatch, response ):
  calls = []

  def fake_post( url, headers, body, timeout ):
    calls.append({'url': url, 'headers': headers, 'body': body})
    return response

  monkeypatch.setattr(ws, '_post_json', fake_post)
  return calls


TAVILY_RESP = {'results': [{'title': 'Healthy meals', 'url': 'https://ex.am/1',
                            'content': 'Fast bowl recipes with good nutrients.'}]}
EXA_RESP = {'results': [{'title': 'Nutrition basics', 'url': 'https://ex.am/2',
                         'text': 'Protein, fiber and fats explained.'}]}


def test_registered_with_params_schema():
  tool = registry.get('web_search')
  assert tool is not None
  assert tool.params['required'] == ['query']
  assert tool.available() is False                    # no key -> gracefully off


def test_tavily_is_default_when_its_key_exists( monkeypatch ):
  monkeypatch.setenv('TAVILY_API_KEY', 'tk')
  monkeypatch.setenv('EXA_API_KEY', 'ek')
  calls = capture_post(monkeypatch, TAVILY_RESP)
  out = ws.web_search('healthy meals', max_results=3)
  assert 'api.tavily.com' in calls[0]['url']
  assert calls[0]['headers']['Authorization'] == 'Bearer tk'
  assert calls[0]['body']['max_results'] == 3
  assert 'Healthy meals' in out and 'https://ex.am/1' in out and 'bowl recipes' in out


def test_exa_used_when_only_its_key_exists( monkeypatch ):
  monkeypatch.setenv('EXA_API_KEY', 'ek')
  calls = capture_post(monkeypatch, EXA_RESP)
  out = ws.web_search('nutrition')
  assert 'api.exa.ai' in calls[0]['url']
  assert calls[0]['headers']['x-api-key'] == 'ek'
  assert 'Nutrition basics' in out and 'fiber' in out


def test_provider_override_wins( monkeypatch ):
  monkeypatch.setenv('TAVILY_API_KEY', 'tk')
  monkeypatch.setenv('EXA_API_KEY', 'ek')
  monkeypatch.setenv('WEB_SEARCH_PROVIDER', 'exa')
  calls = capture_post(monkeypatch, EXA_RESP)
  ws.web_search('q')
  assert 'api.exa.ai' in calls[0]['url']
  assert registry.get('web_search').available() is True


def test_no_key_raises_clear_error():
  with pytest.raises(ValueError, match='TAVILY_API_KEY or EXA_API_KEY'):
    ws.web_search('q')


def test_empty_results_and_result_clamp( monkeypatch ):
  monkeypatch.setenv('TAVILY_API_KEY', 'tk')
  calls = capture_post(monkeypatch, {'results': []})
  assert 'no results' in ws.web_search('q', max_results=99)
  assert calls[0]['body']['max_results'] == 10        # clamped to 1..10
