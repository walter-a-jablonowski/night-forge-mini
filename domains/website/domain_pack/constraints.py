"""Brand / CI constraints — the HARD half (phase 2).

Two layers enforce the operator's invariants, and this module is the second one:

  soft — the free-text `constraints` block is rendered into the system prompt on every
         run (phase 1). Cheap, covers taste, but a model that ignores it writes the
         violation to disk.
  hard — the checks below run INSIDE the write actions, so a violating action fails
         with `status: error` instead of landing. The refusal is logged as an outcome
         and comes back to the model through `history["failures"]` on the next run —
         the same refuse-inside-the-action pattern as the KB pack's create-only
         `add_entry`.

Deliberately separate from `Site`: `Site` is the file API (what a path is, how bytes get
written), this is policy (what content is acceptable). Mixing them would make either one
untestable without the other.

Config (`hard_constraints`, all keys optional):
  forbidden_colors  ["#0000ff", "blue"]   refused in any stylesheet AND in a page's
                                          <style> blocks / style="" attributes
  required_snippets ["assets/logo.svg"]   must survive an edit of a page that had them
  allow_hotlinking  false                 external <img src="http..."> refused

The first two are opt-in: configure nothing and there is nothing to violate. The third
is a FLOOR, active even with no config block at all — an image the site does not own is
a dead link and an unrecorded license, so the default is to refuse it and make the model
go through `add_asset` instead. Set it true to opt out.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

# suffixes whose whole content is CSS (mirrors site.STYLES, kept here so policy does not
# import the file API — the dependency runs the other way)
STYLE_SUFFIXES = {".css"}

# external image reference in page source; `add_asset` + a relative src is the wanted path
_EXTERNAL_IMG = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["'](https?://[^"']+)["']""",
                           re.IGNORECASE)

# the CSS regions of a page: <style> blocks and style="" attributes
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def _inline_css(page: str) -> list[str]:
    """Every CSS fragment embedded in page source, so a stylesheet rule cannot be evaded
    by inlining the same declaration into the HTML."""
    return _STYLE_BLOCK.findall(page) + _STYLE_ATTR.findall(page)


def _color_pattern(color: str) -> re.Pattern:
    """Match a forbidden color only where it is used AS a color, not as a fragment of a
    longer identifier. Plain `in` matching would refuse `.blueberry-card` on a nutrition
    site because "blue" is a substring of it — so require that neither neighbour is a
    word character or a hyphen (`.blue-note` is a class name, `color: blue;` is not)."""
    return re.compile(rf"(?<![\w-]){re.escape(color)}(?![\w-])", re.IGNORECASE)


class HardConstraints:
    """Content policy for the write actions. `check_*` return None when the content is
    acceptable, or a human-readable reason string when it must be refused."""

    def __init__(self, forbidden_colors: list[str] | None = None,
                 required_snippets: list[str] | None = None,
                 allow_hotlinking: bool = False):
        self.forbidden_colors = [str(c).strip().lower() for c in (forbidden_colors or [])
                                 if str(c).strip()]
        self._color_res = [(c, _color_pattern(c)) for c in self.forbidden_colors]
        self.required_snippets = [str(s) for s in (required_snippets or []) if str(s).strip()]
        self.allow_hotlinking = bool(allow_hotlinking)

    @classmethod
    def from_config(cls, raw: Any) -> HardConstraints:
        cfg = raw if isinstance(raw, dict) else {}
        return cls(forbidden_colors=cfg.get("forbidden_colors"),
                   required_snippets=cfg.get("required_snippets"),
                   allow_hotlinking=cfg.get("allow_hotlinking", False))

    def check(self, target: str, content: str, *, previous: str | None = None) -> str | None:
        """THE entry point for the write actions: the rules that apply follow the FILE, not
        the action that happens to be writing it. Binding them to actions instead left
        `forbidden_colors` enforced on `change_design` but skipped when the same stylesheet
        was written through `edit_content` — a hard constraint the model could route around
        by picking the other action, which is exactly what run-9d177565 did."""
        if PurePosixPath(str(target)).suffix.lower() in STYLE_SUFFIXES:
            return self.check_css(content)
        return self.check_page(content, previous=previous)

    def check_css(self, css: str) -> str | None:
        """Forbidden brand colors used as VALUES anywhere in a stylesheet."""
        hits = [c for c, pattern in self._color_res if pattern.search(css)]
        if hits:
            return f"forbidden color(s) {', '.join(hits)} - the brand constraints exclude them"
        return None

    def check_page(self, page: str, *, previous: str | None = None) -> str | None:
        """Page source policy. `previous` is the file's current content on an overwrite:
        a required snippet only has to survive where it already was, so adding the rule
        later never blocks edits to pages that never carried the logo/nav."""
        # A page carries CSS too — in <style> blocks and style="" attributes. Only those
        # regions are checked, never the prose: a nutrition page may write "blue cheese".
        for css in _inline_css(page):
            reason = self.check_css(css)
            if reason:
                return reason
        if not self.allow_hotlinking:
            external = _EXTERNAL_IMG.findall(page)
            if external:
                return (f"external image reference {external[0]} - download it with "
                        "add_asset and reference the local path instead "
                        "(set hard_constraints.allow_hotlinking to permit hotlinking)")
        if previous is not None:
            dropped = [s for s in self.required_snippets if s in previous and s not in page]
            if dropped:
                return f"required element(s) {', '.join(dropped)} removed from the page"
        return None
