"""Unit tests for histogram.py."""
import io

import histogram


def _commits(rows):
    """Inflate compact tuples into per-commit dicts.

    Each row: (repo, date_iso, additions, deletions)
    """
    out = []
    for repo, date, adds, dels in rows:
        out.append({
            "repo": repo,
            "sha": f"sha{len(out)}",
            "date": date,
            "author": "Tester",
            "files_changed": 1,
            "additions": adds,
            "deletions": dels,
            "net": adds - dels,
        })
    return out


def test_summarize_by_repo_aggregates_commits_and_lines():
    commits = _commits([
        ("alpha", "2026-04-01T10:00:00Z", 10, 2),
        ("alpha", "2026-04-02T10:00:00Z", 5, 1),
        ("beta",  "2026-04-01T10:00:00Z", 100, 50),
    ])
    by_repo = {r["repo"]: r for r in histogram.summarize_by(commits, "repo")}
    assert by_repo["alpha"]["commits"] == 2
    assert by_repo["alpha"]["additions"] == 15
    assert by_repo["alpha"]["deletions"] == 3
    assert by_repo["alpha"]["net"] == 12
    assert by_repo["beta"]["commits"] == 1
    assert by_repo["beta"]["net"] == 50


def test_summarize_by_date_truncates_to_day():
    commits = _commits([
        ("a", "2026-04-01T01:00:00Z", 1, 0),
        ("a", "2026-04-01T23:59:59Z", 2, 0),
        ("a", "2026-04-02T00:00:00Z", 4, 0),
    ])
    by_day = {r["date"]: r for r in histogram.summarize_by(commits, "date")}
    assert set(by_day) == {"2026-04-01", "2026-04-02"}
    assert by_day["2026-04-01"]["commits"] == 2
    assert by_day["2026-04-01"]["additions"] == 3
    assert by_day["2026-04-02"]["commits"] == 1


def test_size_distribution_buckets_correctly():
    commits = _commits([
        ("r", "2026-04-01T00:00:00Z", 0, 0),       # 0
        ("r", "2026-04-01T00:00:00Z", 5, 0),       # 1-10
        ("r", "2026-04-01T00:00:00Z", 5, 5),       # 1-10 (10)
        ("r", "2026-04-01T00:00:00Z", 30, 0),      # 11-50
        ("r", "2026-04-01T00:00:00Z", 100, 0),     # 51-200
        ("r", "2026-04-01T00:00:00Z", 500, 0),     # 201-1k
        ("r", "2026-04-01T00:00:00Z", 3000, 0),    # 1k-5k
        ("r", "2026-04-01T00:00:00Z", 10000, 0),   # >5k
    ])
    dist = {r["bucket"]: r["count"] for r in histogram.size_distribution(commits)}
    assert dist == {"0": 1, "1-10": 2, "11-50": 1, "51-200": 1,
                    "201-1k": 1, "1k-5k": 1, ">5k": 1}


def test_render_emits_bars_proportional_to_max():
    rows = [{"repo": "a", "n": 10}, {"repo": "b", "n": 5}, {"repo": "c", "n": 0}]
    buf = io.StringIO()
    histogram.render("Title", rows, "n", "repo", width=10, out=buf)
    out = buf.getvalue()
    assert "Title" in out
    a_line = next(l for l in out.splitlines() if l.startswith("a "))
    b_line = next(l for l in out.splitlines() if l.startswith("b "))
    c_line = next(l for l in out.splitlines() if l.startswith("c "))
    assert a_line.count(histogram.BAR) == 10
    assert b_line.count(histogram.BAR) == 5
    assert c_line.count(histogram.BAR) == 0


def test_render_handles_empty_rows():
    buf = io.StringIO()
    histogram.render("Empty", [], "n", "x", out=buf)
    assert "(no data)" in buf.getvalue()


def test_render_all_handles_empty_commits():
    buf = io.StringIO()
    histogram.render_all([], out=buf)
    assert "(no commits)" in buf.getvalue()


def test_render_all_includes_every_section():
    commits = _commits([
        ("alpha", "2026-04-01T10:00:00Z", 10, 2),
        ("beta",  "2026-04-02T10:00:00Z", 100, 50),
    ])
    buf = io.StringIO()
    histogram.render_all(commits, out=buf)
    out = buf.getvalue()
    for section in [
        "Commits per repo",
        "Lines changed per repo",
        "Commits per day",
        "Additions per day",
        "Commit size distribution",
    ]:
        assert section in out


def test_load_commits_parses_numeric_fields():
    csv_text = (
        "repo,sha,date,author,files_changed,additions,deletions,net\n"
        "alpha,abc123,2026-04-01T10:00:00Z,Tester,3,42,7,35\n"
    )
    rows = histogram.load_commits(io.StringIO(csv_text))
    assert rows[0]["additions"] == 42
    assert rows[0]["deletions"] == 7
    assert rows[0]["net"] == 35
    assert rows[0]["files_changed"] == 3
