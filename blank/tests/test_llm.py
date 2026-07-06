"""ModelWrapper: native structured output with graceful fallback per provider."""
from types import SimpleNamespace

import pytest

from night_forge_mini.llm import ModelWrapper, _extract_json
from night_forge_mini.pack import proposal_schema

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}
REPLY = '{"finding": "f", "actions": []}'


class ParamRejected(Exception):
  status_code = 400


def make_wrapper( handler ):
  """ModelWrapper with a stub client; handler(kwargs) -> content str or raises."""
  calls = []

  def create( **kw ):
    calls.append(kw)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=handler(kw)))])

  w = ModelWrapper(PROVIDER)
  w._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  return w, calls


def test_schema_is_sent_as_response_format():
  w, calls = make_wrapper(lambda kw: REPLY)
  schema = proposal_schema(['add_entry'])
  out = w.complete_json('sys', 'usr', schema=schema)
  assert out == {'finding': 'f', 'actions': []}
  rf = calls[0]['response_format']
  assert rf['type'] == 'json_schema'
  assert rf['json_schema']['schema'] is schema


def test_no_schema_sends_no_response_format():
  w, calls = make_wrapper(lambda kw: REPLY)
  w.complete_json('sys', 'usr')
  assert 'response_format' not in calls[0]


def test_provider_rejection_falls_back_and_is_remembered():
  def handler( kw ):
    if 'response_format' in kw:
      raise ParamRejected('unknown parameter')
    return REPLY

  w, calls = make_wrapper(handler)
  schema = proposal_schema(['add_entry'])
  assert w.complete_json('sys', 'usr', schema=schema) == {'finding': 'f', 'actions': []}
  assert len(calls) == 2 and 'response_format' not in calls[1]

  # rejection is remembered: the next call skips the schema attempt entirely
  w.complete_json('sys', 'usr', schema=schema)
  assert len(calls) == 3 and 'response_format' not in calls[2]


def test_non_param_errors_still_raise():
  class ServerErr(Exception):
    status_code = 500

  def handler( kw ):
    raise ServerErr('boom')

  w, calls = make_wrapper(handler)
  with pytest.raises(ServerErr):
    w.complete_json('sys', 'usr', schema=proposal_schema(['a']))
  assert len(calls) == 1                              # no blind retry on server errors


def test_proposal_schema_shape():
  s = proposal_schema(['add_entry', 'edit_entry'])
  item = s['properties']['actions']['items']
  assert item['properties']['name']['enum'] == ['add_entry', 'edit_entry']
  assert set(item['required']) == {'name', 'target', 'rationale', 'payload'}
  payload = {'type': 'object', 'properties': {'body': {'type': 'string'}}}
  assert proposal_schema(['a'], payload_schema=payload)['properties']['actions']['items']['properties']['payload'] is payload


def test_extract_json_still_tolerates_fenced_prose():
  assert _extract_json('sure!\n```json\n{"a": 1}\n```') == {'a': 1}


def test_client_timeout_and_retries_are_bounded_and_configurable():
  c = ModelWrapper(PROVIDER)._ensure_client()
  assert c.timeout == 120.0 and c.max_retries == 2    # sane defaults, not the SDK's 600s

  tuned = dict(PROVIDER, timeout=5, max_retries=0)
  c = ModelWrapper(tuned)._ensure_client()
  assert c.timeout == 5.0 and c.max_retries == 0
