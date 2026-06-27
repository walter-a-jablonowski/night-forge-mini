"""Optional git versioning of the materialized artifacts (the files a pack writes, e.g.
the KB markdown under data/kb/ or a website under data/site/). The append-only JSONL log
stays the source of truth; git adds file-level history, diffs and easy rollback on top.

This is the **command-line variant**: we shell out to the `git` binary so the operator's
existing auth (SSH keys / credential helper / token) is reused and the app manages no
credentials. A pure-library variant is a future option (see tasks/backlog/git-library.md).

Safety rules (match the loop's "never half-commit" spirit):
  - Disabled unless `config.json` has `"git": {"enabled": true, ...}`.
  - The repo MUST be pre-initialized and rooted exactly at `repo_dir` — we refuse to commit
    if `repo_dir` is merely *inside* another repo (e.g. the project's own source `.git/`).
  - A push failure never breaks the loop: the local commit is kept and we warn.
  - If `git` is missing / repo absent, we skip with a one-time warning, never raise.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class Git:
    def __init__(self, *, enabled: bool, repo_dir: Path | None,
                 granularity: str = "per_run", remote: str = "", branch: str = "main"):
        self.enabled = bool(enabled)
        self.repo_dir = Path(repo_dir) if repo_dir is not None else None
        self.granularity = granularity if granularity in ("per_run", "per_action") else "per_run"
        self.remote = remote or ""
        self.branch = branch or "main"
        self._warned: set[str] = set()

    @classmethod
    def from_config(cls, cfg) -> "Git":
        g = cfg.get("git", {}) or {}
        enabled = bool(g.get("enabled", False))
        repo_dir = cfg.resolve(g.get("repo_dir", "data")) if enabled else None
        return cls(enabled=enabled, repo_dir=repo_dir,
                   granularity=g.get("granularity", "per_run"),
                   remote=g.get("remote", ""), branch=g.get("branch", "main"))

    # --- internals ---------------------------------------------------------

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo_dir), *args],
                              capture_output=True, text=True)

    def _warn(self, msg: str) -> None:
        if msg not in self._warned:
            self._warned.add(msg)
            print(f"night_forge_mini: git: {msg}", file=sys.stderr)

    def available(self) -> bool:
        """True only if git is usable AND repo_dir is the root of its own repo."""
        if not self.enabled or self.repo_dir is None:
            return False
        if shutil.which("git") is None:
            self._warn("`git` not found on PATH; skipping commit")
            return False
        if not self.repo_dir.exists():
            self._warn(f"repo_dir {self.repo_dir} does not exist; skipping commit")
            return False
        top = self._run("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            self._warn(f"{self.repo_dir} is not a git repo — pre-initialize it "
                       f"(`git init` there); skipping commit")
            return False
        if Path(top.stdout.strip()).resolve() != self.repo_dir.resolve():
            # repo_dir is inside a *parent* repo (e.g. the project's source .git/).
            self._warn(f"refusing: repo root {top.stdout.strip()} != repo_dir "
                       f"{self.repo_dir} (never commit to a parent/source repo)")
            return False
        return True

    def is_clean(self) -> bool:
        """True if the working tree + index have no uncommitted changes."""
        st = self._run("status", "--porcelain")
        return st.returncode == 0 and not st.stdout.strip()

    def recoverable(self) -> bool:
        """True when an overwrite/delete in this repo is safely revertible via git, so the
        gate may auto-run an honestly-irreversible action because git supplies the undo:
        versioning on, `per_action` commits (each change is its own revert point), repo
        healthy AND currently clean (the pre-change state is already committed). If any of
        these fails (e.g. a prior commit failed -> dirty), it returns False and the gate
        holds the destructive action instead of risking unrecoverable loss."""
        return (self.enabled and self.granularity == "per_action"
                and self.available() and self.is_clean())

    # --- public ------------------------------------------------------------

    def commit(self, message: str) -> dict[str, Any]:
        """Stage everything under repo_dir and commit; push if a remote is configured.
        Returns a small status dict; never raises."""
        if not self.available():
            return {"status": "skipped", "detail": "git unavailable"}

        add = self._run("add", "-A")
        if add.returncode != 0:
            return self._fail("add", add)

        # Nothing staged -> no commit (e.g. an action that changed no files).
        if self._run("diff", "--cached", "--quiet").returncode == 0:
            return {"status": "noop", "detail": "no changes to commit"}

        commit = self._run("commit", "-m", message)
        if commit.returncode != 0:
            return self._fail("commit", commit)

        out: dict[str, Any] = {"status": "ok", "detail": message}
        if self.remote:
            push = self._run("push", self.remote, self.branch)
            if push.returncode != 0:
                # Push failure must NOT break the loop — keep the local commit, warn.
                self._warn(f"push failed (local commit kept): "
                           f"{push.stderr.strip() or push.stdout.strip()}")
                out["push"] = "failed"
            else:
                out["push"] = "ok"
        return out

    def _fail(self, op: str, proc: subprocess.CompletedProcess) -> dict[str, Any]:
        detail = f"git {op} failed: {proc.stderr.strip() or proc.stdout.strip()}"
        self._warn(detail)
        return {"status": "error", "detail": detail}
