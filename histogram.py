#!/usr/bin/env python3
"""Render ASCII histograms from a per-commit CSV produced by commit-stats.sh.

Usage:
    histogram.py [csv_path]            # path or '-' for stdin
    commit-stats.sh | histogram.py
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from typing import Iterable

BAR = "█"
DEFAULT_WIDTH = 50

SIZE_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0",       0,     0),
    ("1-10",    1,     10),
    ("11-50",   11,    50),
    ("51-200",  51,    200),
    ("201-1k",  201,   1000),
    ("1k-5k",   1001,  5000),
    (">5k",     5001,  None),
]


def render(title: str, rows: list[dict], value_key: str, label_key: str,
           width: int = DEFAULT_WIDTH, out=sys.stdout) -> None:
    print(f"\n{title}", file=out)
    print("=" * len(title), file=out)
    if not rows:
        print("(no data)", file=out)
        return
    max_val = max(r[value_key] for r in rows)
    label_w = max(len(str(r[label_key])) for r in rows)
    val_w = max(len(f"{r[value_key]:,}") for r in rows)
    for r in rows:
        bars = int(round(r[value_key] / max_val * width)) if max_val else 0
        print(f"{str(r[label_key]):<{label_w}}  {r[value_key]:>{val_w},}  {BAR * bars}",
              file=out)


def load_commits(source) -> list[dict]:
    reader = csv.DictReader(source)
    out = []
    for row in reader:
        row["additions"] = int(row["additions"])
        row["deletions"] = int(row["deletions"])
        row["net"] = int(row["net"])
        row["files_changed"] = int(row["files_changed"])
        out.append(row)
    return out


def summarize_by(commits: list[dict], key: str) -> list[dict]:
    agg: dict[str, dict] = defaultdict(
        lambda: {"commits": 0, "additions": 0, "deletions": 0, "net": 0})
    for c in commits:
        k = c[key][:10] if key == "date" else c[key]
        a = agg[k]
        a["commits"] += 1
        a["additions"] += c["additions"]
        a["deletions"] += c["deletions"]
        a["net"] += c["net"]
    return [{key: k, **v} for k, v in agg.items()]


def size_distribution(commits: list[dict]) -> list[dict]:
    sizes = [c["additions"] + c["deletions"] for c in commits]
    rows = []
    for name, lo, hi in SIZE_BUCKETS:
        count = sum(1 for s in sizes if s >= lo and (hi is None or s <= hi))
        rows.append({"bucket": name, "count": count})
    return rows


def render_all(commits: list[dict], width: int = DEFAULT_WIDTH, out=sys.stdout) -> None:
    if not commits:
        print("(no commits)", file=out)
        return

    by_repo = summarize_by(commits, "repo")
    render("Commits per repo",
           sorted(by_repo, key=lambda r: r["commits"], reverse=True),
           "commits", "repo", width=width, out=out)

    for r in by_repo:
        r["lines_changed"] = r["additions"] + r["deletions"]
    render("Lines changed per repo (additions + deletions)",
           sorted(by_repo, key=lambda r: r["lines_changed"], reverse=True),
           "lines_changed", "repo", width=width, out=out)

    by_day = sorted(summarize_by(commits, "date"), key=lambda r: r["date"])
    render("Commits per day", by_day, "commits", "date", width=width, out=out)
    render("Additions per day", by_day, "additions", "date", width=width, out=out)

    render("Commit size distribution (additions + deletions)",
           size_distribution(commits), "count", "bucket", width=width, out=out)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", default="-",
                   help="path to per-commit CSV (default: stdin)")
    p.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                   help=f"max bar width in chars (default: {DEFAULT_WIDTH})")
    return p.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.csv == "-":
        commits = load_commits(sys.stdin)
    else:
        with open(args.csv) as f:
            commits = load_commits(f)
    render_all(commits, width=args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())
