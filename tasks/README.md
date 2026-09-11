
python -m night_forge_mini approve <id>

- only the one action is on halt
- when approved the next run does it

$ run-once        # auto-runs what it can, parks the rest as pending, EXITS (shell returns)
$ inbox           # (optional) see what's held
$ approve <id>    # runs just that held action, logs decision+outcome, EXITS
$ approve <id2>   # each held action approved independently
