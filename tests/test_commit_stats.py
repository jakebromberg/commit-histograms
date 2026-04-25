"""End-to-end tests for commit-stats.sh against a real temp git repo."""
import csv
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import histogram

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "commit-stats.sh"


def _run_script(*args, root: Path) -> str:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--root", str(root), *args],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def _git(cwd: Path, *args, env_extra: dict | None = None) -> None:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Tester",
        "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "Tester",
        "GIT_COMMITTER_EMAIL": "tester@example.com",
    })
    if env_extra:
        env.update(env_extra)
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, env=env)


def _make_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")


def _commit(path: Path, filename: str, content: str, message: str,
            date: str | None = None) -> None:
    (path / filename).write_text(content)
    _git(path, "add", filename)
    env_extra = {}
    if date:
        env_extra["GIT_AUTHOR_DATE"] = date
        env_extra["GIT_COMMITTER_DATE"] = date
    _git(path, "commit", "-q", "-m", message, env_extra=env_extra)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A directory with two repos and a non-repo sibling."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    not_a_repo = tmp_path / "scratch"
    _make_repo(repo_a)
    _make_repo(repo_b)
    not_a_repo.mkdir()

    _commit(repo_a, "hello.txt", "one\ntwo\nthree\n", "first",
            date="2026-04-01T10:00:00Z")
    _commit(repo_a, "hello.txt", "one\ntwo\nthree\nfour\n", "second",
            date="2026-04-02T10:00:00Z")
    _commit(repo_b, "README.md", "# b\n", "init b",
            date="2026-04-03T10:00:00Z")
    return tmp_path


def _parse(csv_text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_emits_one_row_per_commit_with_expected_columns(workspace):
    out = _run_script("--since", "2026-01-01", root=workspace)
    rows = _parse(out)
    assert len(rows) == 3
    assert set(rows[0].keys()) == {
        "repo", "sha", "date", "author",
        "files_changed", "additions", "deletions", "net",
    }


def test_groups_by_repo_basename(workspace):
    out = _run_script("--since", "2026-01-01", root=workspace)
    repos = {r["repo"] for r in _parse(out)}
    assert repos == {"repo-a", "repo-b"}


def test_aggregates_line_counts_per_commit(workspace):
    out = _run_script("--since", "2026-01-01", root=workspace)
    rows = sorted(_parse(out), key=lambda r: r["date"])
    # repo-a first commit: 3 additions, 0 deletions
    assert rows[0]["repo"] == "repo-a"
    assert rows[0]["additions"] == "3"
    assert rows[0]["deletions"] == "0"
    assert rows[0]["net"] == "3"
    # repo-a second commit: 1 addition, 0 deletions
    assert rows[1]["additions"] == "1"
    assert rows[1]["net"] == "1"


def test_since_filter_excludes_old_commits(workspace):
    repo_old = workspace / "repo-old"
    _make_repo(repo_old)
    _commit(repo_old, "ancient.txt", "x\n", "way back",
            date="2020-01-01T00:00:00Z")

    out = _run_script("--since", "2026-01-01", root=workspace)
    repos = {r["repo"] for r in _parse(out)}
    assert "repo-old" not in repos


def test_excludes_merge_commits_by_default(workspace):
    repo = workspace / "repo-a"
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feature.txt", "f\n", "feature work",
            date="2026-04-04T10:00:00Z")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "--no-ff", "-m", "merge feature", "feature",
         env_extra={"GIT_COMMITTER_DATE": "2026-04-05T10:00:00Z"})

    out = _run_script("--since", "2026-01-01", root=workspace)
    msgs = [r for r in _parse(out) if r["repo"] == "repo-a"]
    # 2 original + 1 feature commit, no merge
    assert len(msgs) == 3


def test_include_merges_flag(workspace):
    repo = workspace / "repo-a"
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feature.txt", "f\n", "feature work",
            date="2026-04-04T10:00:00Z")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "--no-ff", "-m", "merge feature", "feature",
         env_extra={"GIT_COMMITTER_DATE": "2026-04-05T10:00:00Z"})

    out = _run_script("--since", "2026-01-01", "--include-merges", root=workspace)
    rows_a = [r for r in _parse(out) if r["repo"] == "repo-a"]
    assert len(rows_a) == 4  # 2 + feature + merge


def test_worktrees_are_deduped(workspace, tmp_path):
    repo_a = workspace / "repo-a"
    worktree = tmp_path / "repo-a-worktree"
    _git(repo_a, "worktree", "add", "-b", "wt-branch", str(worktree))
    _commit(worktree, "wt.txt", "w\n", "worktree commit",
            date="2026-04-06T10:00:00Z")

    out = _run_script("--since", "2026-01-01", root=workspace)
    repos_seen = [r["repo"] for r in _parse(out)]
    # Worktree commit should appear exactly once, attributed to repo-a.
    wt_rows = [r for r in _parse(out)
               if r["repo"] == "repo-a" and r["date"].startswith("2026-04-06")]
    assert len(wt_rows) == 1
    # And there should be no row attributed to the worktree directory's basename.
    assert "repo-a-worktree" not in repos_seen


def test_output_pipes_into_histogram(workspace):
    csv_text = _run_script("--since", "2026-01-01", root=workspace)
    commits = histogram.load_commits(io.StringIO(csv_text))
    buf = io.StringIO()
    histogram.render_all(commits, out=buf)
    rendered = buf.getvalue()
    assert "Commits per repo" in rendered
    assert "repo-a" in rendered
    assert "repo-b" in rendered


def test_help_flag_prints_usage():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        check=True, capture_output=True, text=True,
    )
    assert "Usage" in result.stdout or "usage" in result.stdout.lower()


def test_unknown_flag_errors():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--bogus"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
