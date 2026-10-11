# One pass at a time per deploy

**DONE 2026-10-11.** `run_lock.py`: an OS lock (msvcrt / fcntl) on `<log>.lock`, held for a
pass and for approve/reject. Taken -> `run_once` returns a noop `busy` (the CLI prints
`busy - …`, a `run-loop` tick counts as skipped); approve/reject return an error. Tests
(`test_unattended_guards.py`): exclusive + released, a SECOND PROCESS holding it, an approve
during a pass, and a killed holder leaves no stale lock. Found while testing: on Windows a
venv's `python.exe` is a launcher, so killing it leaves the real interpreter — and its lock —
alive; the test kills the interpreter by pid, and Windows releases the lock shortly after.
Live: a manual `run-once` during a `run-loop` pass on `try/website` was refused.
Consequence for `sqlite-store`: with one writer per deploy, the daemon no longer needs it.

**Effort: XS-S. Blocks unattended use** (0.4.0, before `scheduler-daemon`).

## The gap
Nothing stops two passes running in the same deploy at once. A website pass takes up to
~75 s (600 s CLI timeout); a timer that fires again meanwhile, or a manual `run-once` /
`approve` during a scheduled pass, makes two writers:
- both read the same "new" input (the dedup watermark is derived from the log, and the
  first pass has not written its analysis yet) and process it twice,
- both run actions on the same artifact and both commit to its git repo,
- the JSONL log gets interleaved appends (`sqlite-store.md` notes the missing write lock).

## Shape
An OS file lock (fcntl / msvcrt) on a lock file beside the log, held for the pass — or for
an approve/reject. Not a pid file: a process killed mid-pass (the machine slept during a
live pass on 2026-10-11) must not leave a stale lock, and an OS lock dies with its holder.
A pass that finds the lock taken returns a noop ("another pass is running"), so a
scheduler just skips that tick.

## Relation
`sqlite-store` would give atomic appends, not mutual exclusion of whole passes — this is
needed either way.
