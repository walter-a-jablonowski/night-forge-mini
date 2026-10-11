"""One writer at a time per deploy — a pass, an approve or a reject (tasks/backlog/run-lock.md).

Two passes at once would both read the same "new" input (the dedup watermark is derived
from the log, and the first has not written its analysis yet), both act on the artifact and
both commit to its repo. A scheduler that fires again during a slow pass, or a manual
`run-once` during a scheduled one, is enough.

An OS lock on an open file handle, not a pid file: the lock dies with the process that holds
it, so a pass killed mid-way (the machine went to sleep during one on 2026-10-11) leaves no
stale lock behind. The lock file itself stays; it is empty and means nothing on its own.
"""
from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class RunLock:
    """`with RunLock(path) as held:` — `held` is False when another process has it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._file = None

    def __enter__(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "a+b")
        try:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)   # byte 0; past EOF is fine
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._file = f
        return True

    def __exit__(self, *exc) -> None:
        if self._file is None:
            return
        try:
            if os.name == "nt":
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
