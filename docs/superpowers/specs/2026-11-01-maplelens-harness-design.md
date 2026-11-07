# MapleLens — Phase 0 design: repo + agent harness

Date: 2026-11-01. Status: approved by owner 2026-11-01.

## Intent

An open-source overlay for **MapleStory Classic** (Nexon) that keeps the player
inside the game instead of alt-tabbing to a second screen. Today the owner
keeps open: mesos.watch (market prices), a class guide (gear per level,
training spots, AP/SP), and meowdb's path finder. For EXP/hour at a training
spot, nothing exists.

The overlay will eventually ship four tools, in this order:

1. **EXP meter** — EXP/hour and time-to-level at the current spot. First
   because nothing else does it, and it proves the screen-reading foundation.
2. **Class helper** — the guide's advice for the player's current level.
3. **Prices** — market lookups without leaving the game.
4. **Path arrow** — route shown as an arrow over the game. Last: needs player
   position from the minimap, the riskiest reader.
   (Note: the owner moved the path arrow to second.)

**This document covers only Phase 0:** the repository, its open-source
basics, and the agent harness (Claude Code + other coding agents) that every
later phase is built with. The EXP meter gets its own design next.

## The non-negotiable rule (owner's words: "not let it be a ban risk")

MapleLens is **screen-reading only**. It may capture pixels of the game
window and draw its own separate window on top. It must never:

- read or write game process memory, or inject into / attach to the process
- read, modify, or hook game files or the client's network traffic
- send input (keys/clicks) to the game — no automation of any kind

This rule is the first thing in the agent instructions, the README, and the
contributing guide, and is enforced mechanically (see "Screen-only guard").

## Goals (Phase 0)

- A repo a stranger can clone and run tests in within 5 minutes.
- A fresh agent session (Claude Code, Codex, Cursor…) in the repo knows the
  screen-only rule, the commands, and the layout without being told.
- Violations of the screen-only rule fail CI, regardless of which tool or
  person wrote the code.

## Non-goals (Phase 0)

- No capture, overlay window, readers, or tools yet — those come with the EXP
  meter, where the real shape is known. Phase 0 ships an empty package.
- No GitHub remote / publishing. Repo is local until the owner says push.
- No project skills, subagents, release pipeline, pre-commit hooks,
  commit-message rules. Each is added when the first real need appears
  (see "Deferred").

## Anti-goals

- Anything that a reasonable anti-cheat would flag. If in doubt, leave it out.
- Harness files that only work on the owner's machine (absolute paths,
  personal plugins, personal permissions in committed settings).
- Agent instructions so long nobody — human or model — reads them.

## Constraints

- Windows 10/11 (the game's platform). Game must run windowed or borderless —
  true fullscreen hides overlay windows. Documented in README.
- Open source, MIT license.
- Unofficial fan project; not affiliated with Nexon. Disclaimer in README.

## Decisions

Owner decided: screen-reading only; open source; harness + repo first; EXP
meter next. Everything below marked *(my call)* was delegated to me.

- **Name: `maplelens`** *(my call — trivially renamable before first push)*.
- **Location: `C:\Development\maplelens`** *(my call — next to owner's other
  projects)*. Git repo, default branch `main`.
- **Language: Python 3.12** *(my call)* — most approachable for contributors,
  best screen-capture/vision libraries (mss, OpenCV, numpy), Qt (PySide6) can
  make a transparent click-through always-on-top window. Those libraries are
  added in the EXP meter phase, not now.
- **Tooling** *(my call)*: `uv` for env + deps (one command setup),
  `ruff` for lint + format, `pytest` for tests. Config all in `pyproject.toml`.
- **CI** *(my call)*: one GitHub Actions workflow on `windows-latest`,
  on push to `main` and on every PR: `uv sync`, `ruff check`,
  `ruff format --check`, guard, `pytest`. Made a required check before merge
  (GitHub branch protection — an owner step at push time, not a file).
- **Dependabot** *(owner agreed)*: weekly updates for `uv` deps and GitHub
  Actions.

### Repo layout (Phase 0, exactly this)

```
maplelens/
  AGENTS.md                  # canonical agent instructions (all tools)
  CLAUDE.md                  # one line: @AGENTS.md  (+ Claude-only notes, if any)
  README.md
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md         # Contributor Covenant 2.1, unmodified
  SECURITY.md
  LICENSE                    # MIT
  pyproject.toml
  .gitignore                 # Python + .venv + .claude/settings.local.json
  .github/workflows/ci.yml
  .github/dependabot.yml
  .github/pull_request_template.md
  .github/ISSUE_TEMPLATE/bug_report.yml
  .github/ISSUE_TEMPLATE/feature_request.yml
  .github/ISSUE_TEMPLATE/config.yml   # blank issues off; links SECURITY.md
  .claude/settings.json      # shared, committed
  scripts/check_screen_only.py
  src/maplelens/__init__.py
  tests/test_screen_only_guard.py
  tests/fixtures/screens/.gitkeep
  docs/superpowers/specs/    # this document lives here
```

### Agent instructions: AGENTS.md + CLAUDE.md

AGENTS.md is the single source; CLAUDE.md imports it with `@AGENTS.md` so
there is no duplicated text to drift. Target ≤ 80 lines. Contents, in order:

1. The screen-only rule (verbatim from above) and that the guard enforces it.
2. Commands: setup, test, lint/format, run the guard.
3. Layout: what lives where, including the planned shape for later phases
   (`capture/`, `readers/`, `overlay/`, `tools/<name>/`) marked "not yet".
4. Conventions: readers are pure functions `screenshot -> value` tested
   against PNG fixtures, so tests never need the game running.
5. Fixture policy: crop screenshots to the region a reader needs; never commit
   character names, chat, or other players' info.
6. Don't: add dependencies without need, add banned modules (see guard).

### Shared Claude settings: `.claude/settings.json`

- `permissions.allow`: `uv sync`, `uv run pytest*`, `uv run ruff*`,
  `uv run python scripts/check_screen_only.py*`, `git status`, `git diff*`,
  `git log*`.
- `permissions.deny`: installing known memory/packet libraries
  (e.g. `uv add pymem*`, `pip install pymem*`, and the same for the guard's
  banned list). Belt-and-braces only; the guard is the real enforcement.
- One hook: `PostToolUse` on `Edit|Write` runs the guard, so a Claude session
  sees a violation the moment it writes one.
- No absolute paths, no personal plugins. Personal overrides go in
  `.claude/settings.local.json` (gitignored).

### Screen-only guard

`scripts/check_screen_only.py`: stdlib-only script that scans every `.py`
under `src/` and `scripts/` (excluding itself) and fails with file:line on:

- imports of known process-memory / injection / packet-capture modules:
  `pymem`, `frida`, `scapy`, `pydivert`, `pywinauto`, `pyautogui`,
  `pynput`, `keyboard`, `mouse`, `win32process`, `pyshark`, `pydirectinput`,
  `ahk`, `interception`, `vgamepad`, `ReadWriteMemory` — also when loaded via
  `__import__("x")` / `import_module("x")` with a literal name
  (input-sending libraries are banned because the overlay must never drive
  the game; overlay hotkeys will use Qt's own shortcut handling)
- string references to Win32 calls: `ReadProcessMemory`,
  `WriteProcessMemory`, `OpenProcess`, `VirtualAllocEx`,
  `CreateRemoteThread`, `SendInput`, `SetWindowsHookEx`, `keybd_event`,
  `mouse_event`, `PostMessage`, `SendMessage`, `SendMessageTimeout`,
  `SendMessageCallback`, `SendNotifyMessage`, `PostThreadMessage`,
  `NtReadVirtualMemory`, `NtWriteVirtualMemory`, `DebugActiveProcess`

It is a speed bump against honest mistakes, not a security boundary; README
says so. Runs in CI and in the Claude hook. The banned list lives in the
script, with a comment explaining each entry.

`tests/test_screen_only_guard.py`: writes a temp file containing a banned
import and a banned Win32 name, asserts the guard fails on both; asserts it
passes on the real repo.

### Open-source files

- **README**: one-paragraph pitch; the screen-only promise; "unofficial, not
  affiliated with Nexon"; windowed/borderless requirement; setup in 3
  commands; roadmap (the four tools, in order); status: "Phase 0 — nothing
  to run yet".
- **CONTRIBUTING** *(owner agreed: a real how-to)*: the screen-only rule
  first; flow fork → branch → PR; setup in 3 commands; running tests, lint and
  the guard; adding a fixture screenshot (crop to the region, no names/chat,
  note resolution + UI scale in the filename); what a good PR looks like
  (small, one tool or reader, tests included); AI-agent policy: welcome, the
  agent reads AGENTS.md automatically, but the contributor is responsible for
  the code and must have run it.
- **PR template**: short description + checklist — tests pass; guard passes;
  no new banned libraries; fixtures cropped; "this change only reads the
  screen and draws its own window".
- **Issue templates** (YAML forms): bug report (what happened, expected,
  cropped screenshot, game resolution, UI scale, windowed/borderless,
  MapleLens version/commit); feature or tool idea (the in-game moment it
  helps, what you use today instead). Blank issues disabled; config links to
  SECURITY.md for private reports.
- **CODE_OF_CONDUCT**: Contributor Covenant 2.1, unmodified; enforcement
  contact = owner's email (ask at build time).
- **SECURITY.md**: report privately via GitHub private vulnerability
  reporting; in scope: security bugs **and** any code that could get players
  banned (anything breaking the screen-only rule). Those are treated the same.
- **LICENSE**: MIT, copyright holder = owner's name (ask at build time).

Files are read as UTF-8 with an optional BOM (`utf-8-sig`).
*(Lists extended after final review, 2026-11-01.)*

## Done means

- `uv sync && uv run pytest && uv run ruff check` pass on a clean clone.
- The guard test proves it catches a planted violation.
- A fresh Claude Code session asked "what am I not allowed to do here?"
  answers with the screen-only rule without opening any file by hand.
- Initial commit on `main`; nothing pushed.

## Deferred (and when to add)

- Project skills (`add-reader`, `add-tool`): write alongside the first real
  reader in the EXP meter phase — a recipe written before the pattern exists
  will be wrong.
- Reviewer subagent for the screen-only rule: only if the guard misses
  something real.
- Release/packaging (PyInstaller exe) workflow: when the EXP meter works. *Done
  2026-11-06: see `2026-11-06-windows-installer-design.md`.*
- Pre-commit hooks: only if CI catches lint failures often enough to annoy.
- Commit-message rules / changelog tooling: when releases start.
- CodeQL: a toggle in GitHub settings once public; no file needed.

## Owner steps at push time (not files)

- Create the GitHub repo and push.
- Branch protection on `main`: require the CI check, require a PR.
- Enable private vulnerability reporting and (optionally) CodeQL default setup.

## Left to the builder

File wording, exact ruff rule set, CI caching, guard implementation details
(AST vs regex) as long as it reports file:line and is stdlib-only.

## Open questions for later phases (not blocking Phase 0)

- Do mesos.watch / meowdb offer data in a usable form, and do they permit it?
- Nexon's terms on overlays / screen capture for MapleStory Classic.
- Shipping small digit/icon templates cropped from game screenshots — fine
  for a fan project, or generate them at first run from the user's screen?
