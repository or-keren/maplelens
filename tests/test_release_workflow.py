"""release.yml must check and build before it publishes, and publish a version only once.
prepare-release.yml must check before it pushes, and refuse a version already in flight.

The fork runs are the real test; these keep the files from drifting away from ci.yml.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _run_lines(path: Path) -> list[str]:
    """The commands of a workflow's single-line `run:` steps, in order."""
    return re.findall(r"^\s*-?\s*run: (\S.*)$", path.read_text(encoding="utf-8"), re.M)


def _release() -> str:
    return (WORKFLOWS / "release.yml").read_text(encoding="utf-8")


def test_runs_every_ci_check_before_publishing():
    text = _release()
    publish = text.index("gh release create")
    for check in _run_lines(WORKFLOWS / "ci.yml"):
        if check.startswith("uv run"):
            assert -1 < text.find(check) < publish, check


def test_builds_with_the_build_group_before_publishing():
    text = _release()
    publish = text.index("gh release create")
    assert -1 < text.find("uv sync --locked --group build") < publish
    assert -1 < text.find("scripts/build_installer.py") < publish


def test_publish_attaches_the_setup_exe_with_generated_notes():
    publish = _release().split("gh release create", 1)[1].split("\n\n", 1)[0]
    assert "MapleLens-Setup-" in publish
    assert "--generate-notes" in publish


def test_only_on_push_to_main_and_never_two_at_once():
    text = _release()
    assert re.search(r"^on:\n  push:\n    branches: \[main\]\n", text, re.M)
    assert re.search(r"^concurrency:", text, re.M)
    assert "contents: write" in text


def test_stops_when_the_tag_exists():
    text = _release()
    assert "git ls-remote" in text
    assert "already released" in text
    assert text.index("already released") < text.index("gh release create")


def _prepare() -> str:
    return (WORKFLOWS / "prepare-release.yml").read_text(encoding="utf-8")


def test_prepare_is_started_by_hand_with_a_bump_choice():
    text = _prepare()
    assert re.search(r"^on:\n  workflow_dispatch:\n", text, re.M)
    assert re.search(r"options: \[patch, minor, major\]", text)
    assert "BUMP: ${{ inputs.bump }}" in text  # through env, never pasted into the script


def test_prepare_bump_never_relocks():
    # the runner's uv may be newer than the one that wrote uv.lock, and re-locking would
    # rewrite the lock's format too, so the PR diff would be more than the version lines
    text = _prepare()
    assert 'uv version --bump "$BUMP" --frozen' in text
    assert "uv lock" not in text
    assert text.index("--frozen") < text.index("run: uv sync --locked")


def test_prepare_refuses_a_version_already_in_flight_before_pushing():
    text = _prepare()
    push = text.index("git push")
    for check in ["refs/tags/v", "refs/heads/release/v", "gh pr list"]:
        assert -1 < text.find(check) < push, check


def test_prepare_runs_every_ci_check_before_pushing():
    text = _prepare()
    push = text.index("git push")
    for check in _run_lines(WORKFLOWS / "ci.yml"):
        assert -1 < text.find(check) < push, check


def test_prepare_commits_only_the_version_and_opens_the_pr():
    text = _prepare()
    assert 'git commit pyproject.toml uv.lock -m "release: v$VERSION"' in text
    assert text.index("git push") < text.index("gh pr create")
    assert "contents: write" in text
    assert "pull-requests: write" in text


def _job(text: str, name: str) -> str:
    """The text of job `name` in a workflow, up to the next job."""
    return re.split(r"^  (?=\w)", text.split(f"\n  {name}:\n", 1)[1], flags=re.M)[0]


def test_the_build_can_only_read_and_publish_runs_no_build_code():
    # every installed copy runs what this publishes: downloaded packages and hooks run in
    # `build`, which can't write; `publish` only fetches the exe and runs gh
    text = _release()
    build, publish = _job(text, "build"), _job(text, "publish")
    assert "contents: read" in build
    assert "contents: write" not in build
    assert build.count("persist-credentials: false") == 1
    assert "scripts/build_installer.py" in build
    assert "timeout-minutes:" in build
    assert "contents: write" in publish
    assert "gh release create" in publish
    assert "actions/checkout" not in publish
    assert "uv " not in publish


def test_actions_are_pinned_to_commits():
    for path in WORKFLOWS.glob("*.yml"):
        for ref in re.findall(r"uses: (\S+)", path.read_text(encoding="utf-8")):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), (path.name, ref)


def test_a_failed_tag_lookup_fails_rather_than_rebuilding():
    # git ls-remote --exit-code: 2 means no such tag; 128 (a network error) must not
    text = _job(_release(), "version")
    assert '"$code" -eq 2' in text
    assert "exit 1" in text
