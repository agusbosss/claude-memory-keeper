# claude-memory-keeper

**Keep [Claude Code](https://claude.com/claude-code) project memories connected when you move, rename, or reorganize project folders.**

Claude Code stores each project's memory and session history under a key derived from the folder's **absolute path**. Move or rename the folder and that key changes — so the memory gets orphaned and Claude no longer finds it. This tool fixes that: it gives every project a stable **ID that travels inside the folder**, and reconnects the memory automatically whenever a folder moves.

> The tool is written in Spanish (comments and CLI output). This README is in English. Everything is plain Python 3, no dependencies.

---

## The problem

Claude Code keeps project data here:

```
~/.claude/projects/<key>/
        ├── memory/       ← the memories (.md files)
        └── *.jsonl       ← session transcripts
```

`<key>` is the project's absolute path with every non-alphanumeric character turned into `-`:

| Folder on disk | Key |
|---|---|
| `/Users/you/Developer/my-app` | `-Users-you-Developer-my-app` |

Because the link **is** the path, moving or renaming the folder changes the key and **disconnects the memory**. It isn't deleted — just orphaned.

## The solution: a portable project ID

Two pieces:

- **The ID** — a hidden `.claude-project-id` file at the project root, holding a unique id that never changes and **moves with the folder**.
- **The registry** — a central `~/.claude/project-registry.json` that remembers, per ID, where it last lived (path + key) and a history of moves.

With those, at any time the tool can: scan for the IDs, compare "where the ID is now" vs "where the registry said it was", and if they differ → copy the memory to the new key and update the registry. Like a national ID: you change address (path), your ID stays the same, you just update the registry.

## How it works day to day

- **Creating / using a project → do nothing.** A `SessionStart` hook stamps the ID the first time you open Claude Code in a folder, so every project is enrolled from the start.
- **Moving / reorganizing → one step.** Rearrange folders freely, then run `reconcile` (or invoke the skill). Everything reconnects and you get a summary of what moved.

---

## Install

1. Copy the engine:
   ```bash
   mkdir -p ~/.claude/scripts
   cp claude_projects.py ~/.claude/scripts/
   chmod +x ~/.claude/scripts/claude_projects.py
   ```
2. Set your watched roots — edit `DEFAULT_ROOTS` near the top of `claude_projects.py` (or `_config.roots` in the registry once created).
3. Add the auto-enroll hook to `~/.claude/settings.json`, inside `"hooks"`:
   ```json
   "SessionStart": [
     { "hooks": [ { "type": "command",
       "command": "python3 \"$HOME/.claude/scripts/claude_projects.py\" enroll \"${CLAUDE_PROJECT_DIR:-$PWD}\" >/dev/null 2>&1 || true" } ] }
   ]
   ```
4. Enroll everything you already have:
   ```bash
   python3 ~/.claude/scripts/claude_projects.py reconcile
   ```
5. *(Optional)* Install the Claude Code skill so you can say "I moved folders, reorganize memories":
   ```bash
   mkdir -p ~/.claude/skills/reordenar-memorias
   cp SKILL.md ~/.claude/skills/reordenar-memorias/
   ```

## Usage

```bash
# Reconnect everything that moved + enroll new projects (the main command)
python3 ~/.claude/scripts/claude_projects.py reconcile

# Show the registry (which project lives where + move count)
python3 ~/.claude/scripts/claude_projects.py status

# Enroll / reconnect a single folder (this is what the hook runs)
python3 ~/.claude/scripts/claude_projects.py enroll "/path/to/project"
```

There's also `claude-mv-project.sh`, a standalone helper to move **one** project by giving the old and new paths explicitly (moves the folder and reconnects the memory in one shot).

---

## Important: path encoding on macOS

This is the subtle part. macOS stores filenames in Unicode **NFD** (decomposed). Claude Code normalizes the path to **NFC** and replaces every non-ASCII-alphanumeric character with `-` — accents included:

```
Estadística  →  Estad-stica
```

So the key function must normalize to NFC first and use ASCII-only alphanumerics. Do **not** use Python's `str.isalnum()` (it keeps accents and produces the wrong key). The tool already does this correctly:

```python
import unicodedata
def enc(path):
    path = unicodedata.normalize("NFC", path)
    return "".join(c if (c.isascii() and c.isalnum()) else "-" for c in path)
```

## Safety

- It **never deletes** memory. When it reconnects, it **archives** the old key under `~/.claude/projects-archive/` (timestamped).
- When copying, it does **not overwrite** files that already exist at the destination.
- Nested projects are supported.
- If after reconnecting you open Claude in the folder and it doesn't remember, the real key differs — check the name created under `~/.claude/projects/` and adjust.

## Files

| File | Role |
|---|---|
| `claude_projects.py` | Engine: `enroll` / `reconcile` / `status` |
| `claude-mv-project.sh` | Standalone single-project mover (old → new path) |
| `SKILL.md` | Optional Claude Code skill wrapper |
| `project-registry.example.json` | Example of what the registry looks like |

## License

MIT — see [LICENSE](LICENSE).
