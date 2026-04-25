# commit-histograms

ASCII histograms of git commit activity across a directory of repositories.

Two scripts:

- `commit-stats.sh` — walks every git repo one level under a root and emits a per-commit CSV. Worktrees are deduped against their parent repo by `git common-dir`.
- `histogram.py` — reads the CSV (or stdin) and prints histograms for commits per repo, lines changed per repo, commits per day, additions per day, and a commit-size distribution.

## Usage

```sh
./commit-stats.sh --root ~/Developer/WXYC --since '30 days ago' > commits.csv
./histogram.py commits.csv
```

Or piped:

```sh
./commit-stats.sh --root . | ./histogram.py
```

### `commit-stats.sh` options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--root DIR` | `.` | Directory whose immediate children are scanned for git repos. |
| `--since DATE` | `30 days ago` | Anything `git log --since` accepts (`'2 weeks ago'`, `2026-01-01`, …). |
| `--include-merges` | off | Include merge commits in the output. |

CSV columns: `repo, sha, date, author, files_changed, additions, deletions, net`.

### `histogram.py` options

| Flag | Default | Meaning |
| --- | --- | --- |
| `csv` | `-` (stdin) | Path to the per-commit CSV. |
| `--width N` | `50` | Maximum bar width in characters. |

## Tests

```sh
pip install pytest
pytest
```

Tests build a real temporary git repo, exercise `commit-stats.sh` end-to-end, and assert on the histogram output.

## Requirements

`bash`, `git`, `awk`, Python 3.10+. No third-party Python dependencies for runtime.
