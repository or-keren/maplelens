# Contributing to MapleLens

Thanks for helping. Please read the rule below first. It's the one thing we never bend.

## The rule

MapleLens is **screen-reading only**. It may capture pixels of the game
window and draw its own separate window on top. It must never:

- read or write game process memory, or inject into / attach to the process
- read, modify, or hook game files or the client's network traffic
- send input (keys/clicks) to the game — no automation of any kind

Breaking this can get players banned. Pull requests that break it are closed,
however useful the feature. If you're not sure whether an idea crosses the
line, open an issue and ask first.

## Setup

You need [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`).

```
git clone https://github.com/<you>/maplelens.git
cd maplelens
uv sync
```

## Checks (CI runs exactly these)

```
uv run ruff check
uv run ruff format --check                   # `uv run ruff format` fixes it
uv run python scripts/check_screen_only.py   # screen-only guard
uv run pytest
```

## Workflow

1. Fork the repo and create a branch: `git checkout -b exp-meter-level-reader`.
2. Make your change, with tests.
3. Run the checks above.
4. Open a pull request and fill in the template. The `check` job must pass.

## What a good pull request looks like

- **Small:** one tool, one reader, or one fix.
- **Tested:** readers come with fixture screenshots and a test that reads them.
- **Explained:** what in-game moment it helps, and how you tested it in game, if you did.

## Adding a fixture screenshot

Readers are tested against saved screenshots, so nobody needs the game open to run tests.

- Crop to the region the reader needs (EXP bar, minimap…), never the full screen.
- **Never** include character names, chat, or other players' info.
- Put resolution and UI scale in the filename, e.g. `exp_bar_1366x768_100.png`.
- Save under `tests/fixtures/screens/`.

## Building the Windows installer

On Windows, with [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup --scope user`):

```
uv run --group build python scripts/build_installer.py   # --freeze-only: just dist\MapleLens\
```

It writes `dist\MapleLens-Setup-X.Y.Z.exe` and fails if the app is missing data or
`MapleLens.exe --self-check` fails. You don't need it for a pull request; the release
workflow builds the installer itself.

## Testing an update

The installed app asks `or-keren/maplelens` for its latest release. Point it at your
fork instead: never test against or-keren's releases, which players see.

1. Build version N and install it.
2. Set the repo for your user, then start MapleLens from the Start menu so it picks the
   variable up:

   ```
   setx MAPLELENS_UPDATE_REPO <you>/maplelens
   ```

3. Bump the version in `pyproject.toml` for the build only (don't commit it), build N+1,
   and publish it on your fork by hand. GitHub computes the asset's digest itself.

   ```
   gh release create vN+1 dist\MapleLens-Setup-N+1.exe --repo <you>/maplelens
   ```

4. Start N. Within seconds the box offers N+1. Click **Update to N+1…**, and MapleLens
   comes back as N+1 with your settings and history.
5. Clean up: delete the test release and its tag, and the variable.

   ```
   gh release delete vN+1 --repo <you>/maplelens --cleanup-tag --yes
   reg delete HKCU\Environment /v MAPLELENS_UPDATE_REPO /f
   ```

Run from source, MapleLens never checks. The update code is tested without the network:
`tests/test_update.py` reads the saved replies in `tests/fixtures/github/`, and
`tests/test_app.py` gives the check fake requests, downloads and setups, a tampered one
included.

## Making a release (maintainers)

The version lives in `pyproject.toml`. Don't change it by hand: a new version reaching
`main` publishes a release.

1. **Actions → Prepare release → Run workflow**, on `main`, and pick `patch`, `minor` or
   `major`. It bumps the version, runs the checks and opens PR `release: vX.Y.Z`, which
   changes only the version lines in `pyproject.toml` and `uv.lock`. It refuses if that
   version is already tagged or a release PR is already open.
2. **Merge the PR.** That's the approval. The Release workflow then builds
   `MapleLens-Setup-X.Y.Z.exe`, tags `vX.Y.Z` and publishes the GitHub Release with
   notes listing the PRs merged since the last one. To not release, close the PR and
   delete its branch.

The release PR shows no checks of its own, because GitHub doesn't start CI for a PR that
a workflow opened. The checks ran in the Prepare release run, which the PR links to. If
`main` requires status checks, close and reopen the PR to start CI.

If the Release workflow fails, nothing is tagged or published. Fix the cause in a normal
PR; the next push to `main` tries the release again.

One-time setup: **Settings → Actions → General → Allow GitHub Actions to create and
approve pull requests**, or Prepare release can't open its PR.

## Using an AI coding agent

Welcome. Claude Code, Codex, Cursor and similar tools read `AGENTS.md`
automatically, so they know the rule and the commands. You don't have to set
anything up. Claude Code also runs the guard after every edit.

You're still responsible for what you submit: read the code, run it, and make sure it
does what the PR says.

## Reporting problems

- **Bugs and ideas:** open an issue from the templates.
- **Security problems, or code that could get players banned:** don't open a public
  issue. See [SECURITY.md](SECURITY.md).

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
