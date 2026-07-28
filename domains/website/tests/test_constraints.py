"""Hard brand/CI constraints and the add_asset licensing ladder — pure policy, no files."""
import pytest

from domain_pack.assets import AssetPolicy, sidecar_text
from domain_pack.constraints import HardConstraints


# --- brand constraints ------------------------------------------------------

def test_absent_config_disables_the_operator_rules_but_not_the_hotlink_floor():
  # forbidden_colors / required_snippets are opt-in (nothing configured -> nothing to
  # violate), but no-hotlinking is the DEFAULT: images belong in the repo, downloaded
  # through add_asset with their provenance recorded.
  hard = HardConstraints.from_config(None)
  assert hard.check_css('body { color: blue; }') is None
  assert hard.check_page('<p>anything</p>', previous='<img src="assets/logo.svg">') is None
  assert hard.check_page('<img src="https://ex.am/x.jpg">') is not None


def test_forbidden_colors_refused_case_insensitively():
  hard = HardConstraints(forbidden_colors=['#0000FF', 'blue'])
  reason = hard.check_css('a { color: #0000ff; }')
  assert reason and '#0000ff' in reason
  assert hard.check_css('.card { background: BLUE; }') is not None
  assert hard.check_css('a { color: goldenrod; }') is None


def test_forbidden_colors_match_whole_words_not_substrings():
  # a nutrition site legitimately talks about blueberries; a substring match would
  # refuse every stylesheet that names one
  hard = HardConstraints(forbidden_colors=['blue'])
  assert hard.check_css('.blueberry-card { background: #2a2a2a; }') is None
  assert hard.check_css('/* blueberries are rich in antioxidants */') is None
  assert hard.check_css('.blue-note { color: gold; }') is None      # class name, not a color
  assert hard.check_css('a { color: blue; }') is not None           # an actual color value


def test_required_snippet_must_survive_an_edit_that_had_it():
  hard = HardConstraints(required_snippets=['assets/logo.svg'])
  before = '<header><img src="assets/logo.svg"></header><p>old</p>'
  assert hard.check_page(before, previous=before) is None
  reason = hard.check_page('<p>new</p>', previous=before)
  assert reason and 'assets/logo.svg' in reason


def test_required_snippet_does_not_block_pages_that_never_had_it():
  # adding the rule later must not freeze every page that predates it
  hard = HardConstraints(required_snippets=['assets/logo.svg'])
  assert hard.check_page('<p>new</p>', previous='<p>old</p>') is None
  assert hard.check_page('<p>brand new page</p>') is None


def test_hotlinked_images_refused_by_default_and_allowed_by_switch():
  hard = HardConstraints()
  reason = hard.check_page('<img src="https://ex.am/x.jpg" alt="x">')
  assert reason and 'add_asset' in reason
  assert hard.check_page('<img src="assets/x.jpg">') is None       # local is fine
  assert HardConstraints(allow_hotlinking=True).check_page(
    '<img src="https://ex.am/x.jpg">') is None


# --- asset licensing ladder -------------------------------------------------

OPEN = {'license': 'by-sa 4.0', 'creator': 'Jane', 'source': 'https://ex.am/p'}


def test_operator_host_needs_no_license():
  policy = AssetPolicy(allowed_hosts=['example.org'])
  assert policy.check('https://example.org/logo.svg', {}) is None
  assert policy.check('https://cdn.example.org/logo.svg', {}) is None   # subdomain
  assert policy.check('https://notexample.org/logo.svg', {}) is not None


def test_open_license_is_accepted_and_restrictive_ones_are_not():
  policy = AssetPolicy()
  assert policy.check('https://any.host/x.jpg', OPEN) is None
  for bad in ('by-nc', 'by-nd 4.0', 'by-nc-sa'):
    reason = policy.check('https://any.host/x.jpg', {'license': bad})
    assert reason and 'commercial use' in reason


def test_missing_license_from_an_unknown_host_is_refused():
  reason = AssetPolicy().check('https://any.host/x.jpg', {})
  assert reason and 'image_search' in reason


def test_non_http_scheme_refused():
  assert AssetPolicy().check('file:///etc/passwd', OPEN) is not None


def test_sidecar_records_the_full_provenance():
  text = sidecar_text('https://any.host/x.jpg', {**OPEN, 'attribution': 'by Jane, CC BY-SA'})
  assert 'https://any.host/x.jpg' in text
  assert 'by-sa 4.0' in text and 'Jane' in text and 'CC BY-SA' in text
  assert sidecar_text('https://any.host/x.jpg', {}).strip().endswith('x.jpg')  # url only
