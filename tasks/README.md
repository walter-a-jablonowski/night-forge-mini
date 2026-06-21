# How `/tasks` works (for agents)

- **`-this.md`** — the active worklist. Usually **user-edited** (source of intent); the agent edits it only when the user asks.
- **`backlog/`** — one file per issue/feature. **Agent-edited often**; user may add items too.
- **`resources/`** — information-only docs + large task details linked from elsewhere. Reference, no tasks.
- **`v done/`** — completed tasks (file or folder, date-prefixed). **Ignore** unless asked.
