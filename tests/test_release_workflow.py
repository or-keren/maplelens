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


def _steps(job: str) -> list[str]:
    """The steps of a job, each as its text."""
    return re.split(r"^      - ", job.split("    steps:\n", 1)[1], flags=re.M)[1:]


def _step_index(steps: list[str], needle: str) -> int:
    return next(i for i, s in enumerate(steps) if needle in s)


def _builds_on_both_macs(job: str) -> None:
    """Apple silicon and Intel, each with the dmg name maplelens.update looks for."""
    assert "runs-on: ${{ matrix.runner }}" in job
    assert re.search(r"- runner: macos-latest\n\s+arch: arm64\n\s+dmg: \"\"\n", job)
    assert re.search(r"- runner: macos-15-intel\n\s+arch: x86_64\n\s+dmg: -intel\n", job)


def test_mac_build_can_only_read_and_sees_no_secrets():
    job = _job(_release(), "mac-build")
    _builds_on_both_macs(job)
    assert "contents: read" in job
    assert "contents: write" not in job
    assert "secrets." not in job
    assert job.count("persist-credentials: false") == 1
    assert "--freeze-only" in job
    assert "ditto -c -k --keepParent dist/MapleLens.app" in job
    assert "name: mac-app-${{ matrix.arch }}" in job


def test_only_mac_sign_sees_the_certificate():
    text = _release()
    for name in ["version", "build", "mac-build", "publish"]:
        assert "secrets." not in _job(text, name), name
    sign = _job(text, "mac-sign")
    assert "secrets.MAC_SIGN_P12_BASE64" in sign
    assert "secrets.MAC_SIGN_P12_PASSWORD" in sign
    assert "contents: write" not in sign
    assert "persist-credentials: false" in sign


def test_mac_sign_signs_on_the_mac_that_built_the_app():
    sign = _job(_release(), "mac-sign")
    _builds_on_both_macs(sign)
    assert "name: mac-app-${{ matrix.arch }}" in sign
    assert "path: dist/MapleLens-${{ env.VERSION }}${{ matrix.dmg }}.dmg" in sign


def test_mac_sign_installs_no_packages():
    sign = _job(_release(), "mac-sign")
    assert "setup-uv" not in sign
    assert not re.search(r"\buv\b|\bpip\b|brew install", sign)
    assert "python3 scripts/build_installer.py --sign-only" in sign
    assert "sys.version_info >= (3, 11)" in sign  # fails clearly on an old python3


def test_mac_sign_deletes_the_keychain_before_running_the_app():
    steps = _steps(_job(_release(), "mac-sign"))
    delete = steps[_step_index(steps, "security delete-keychain")]
    assert re.search(r"^\s+if: always\(\)", delete, re.M)
    sign = _step_index(steps, "--sign-only")
    assert sign < _step_index(steps, "security delete-keychain") < _step_index(steps, "--dmg-only")
    assert "MAPLELENS_SIGN_IDENTITY: MapleLens Release" in steps[sign]
    assert "name: mac-dmg-${{ matrix.arch }}" in steps[-1]


def test_mac_sign_makes_the_identity_usable_and_cleans_up_the_key_files():
    steps = _steps(_job(_release(), "mac-sign"))
    imp = steps[_step_index(steps, "security import")]
    assert "$RUNNER_TEMP" in imp
    assert "set-key-partition-list" in imp
    assert "-T /usr/bin/codesign" in imp
    assert "list-keychains -d user -s" in imp  # on the search list, keeping the others
    assert "add-trusted-cert -d -r trustRoot -p codeSign" in imp
    assert "rm -f" in imp
    assert "ditto -x -k" in steps[_step_index(steps, "ditto -x -k")]


def test_mac_sign_fails_without_the_certificate():
    steps = _steps(_job(_release(), "mac-sign"))
    check = steps[_step_index(steps, "::error::")]
    assert "MAC_SIGN_P12_BASE64" in check and "MAC_SIGN_P12_PASSWORD" in check
    assert _step_index(steps, "::error::") < _step_index(steps, "security import")
    # secrets go in through env, never into the command line
    assert not re.search(r"run:.*\$\{\{\s*secrets", check)


def test_publish_attaches_the_exe_and_both_dmgs():
    text = _release()
    publish = _job(text, "publish")
    assert "mac-sign" in publish.split("steps:", 1)[0]
    assert "pattern: mac-dmg-*" in publish
    assert "merge-multiple: true" in publish
    cmd = publish.split("gh release create", 1)[1]
    assert "MapleLens-Setup-$VERSION.exe" in cmd
    assert '"dist/MapleLens-$VERSION.dmg"' in cmd
    assert '"dist/MapleLens-$VERSION-intel.dmg"' in cmd


def test_ci_checks_on_both_macs():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "os: [windows-latest, macos-latest, macos-15-intel]" in ci


def test_mac_sign_uses_only_apple_tools_and_a_failed_delete_fails_the_job():
    steps = _steps(_job(_release(), "mac-sign"))
    assert "openssl" not in "".join(steps)
    imp = steps[_step_index(steps, "security import")]
    assert "security find-certificate -c" in imp
    assert "sudo security add-trusted-cert -d -r trustRoot -p codeSign" in imp
    delete = steps[_step_index(steps, "security delete-keychain")]
    assert "|| true" not in delete
    assert "rm -f" in delete
