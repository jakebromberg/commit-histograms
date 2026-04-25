#!/usr/bin/env bash
# Emit a per-commit CSV across every git repo under ROOT, dedup'd by common .git dir
# so worktrees don't double-count.
#
# Usage:
#   commit-stats.sh [--root DIR] [--since DATE] [--include-merges] > commits.csv
#
# Defaults: --root=.  --since='30 days ago'

set -euo pipefail

ROOT="."
SINCE="30 days ago"
NO_MERGES="--no-merges"

while [ $# -gt 0 ]; do
    case "$1" in
        --root)            ROOT="$2"; shift 2 ;;
        --since)           SINCE="$2"; shift 2 ;;
        --include-merges)  NO_MERGES=""; shift ;;
        -h|--help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [ ! -d "$ROOT" ]; then
    echo "root not found: $ROOT" >&2
    exit 2
fi

echo "repo,sha,date,author,files_changed,additions,deletions,net"

declare -A SEEN
for d in "$ROOT"/*/; do
    [ -d "$d/.git" ] || [ -f "$d/.git" ] || continue
    common=$(git -C "$d" rev-parse --git-common-dir 2>/dev/null) || continue
    abs=$(cd "$d" && cd "$common" && pwd -P)
    if [ -z "${SEEN[$abs]:-}" ]; then
        # Prefer the working dir whose name matches the parent of the .git dir
        # (so the canonical checkout wins over its worktrees).
        parent_name=$(basename "$(dirname "$abs")")
        candidate="$ROOT/$parent_name"
        if [ -d "$candidate/.git" ] || [ -f "$candidate/.git" ]; then
            SEEN[$abs]="$candidate"
        else
            SEEN[$abs]="${d%/}"
        fi
    fi
done

for abs in "${!SEEN[@]}"; do
    repo="${SEEN[$abs]}"
    repo_name=$(basename "$repo")

    # All refs (local + remote) so in-progress branches count. Author timestamp.
    git -C "$repo" log --all --since="$SINCE" $NO_MERGES \
        --pretty=format:"COMMIT|%H|%aI|%an" --numstat 2>/dev/null \
    | awk -F'|' -v repo="$repo_name" '
        /^COMMIT\|/ {
            if (sha != "") {
                printf "%s,%s,%s,\"%s\",%d,%d,%d,%d\n",
                    repo, sha, date, author, files, adds, dels, adds-dels
            }
            sha=$2; date=$3; author=$4
            gsub(/"/, "\"\"", author)
            files=0; adds=0; dels=0
            next
        }
        /^[0-9-]+\t[0-9-]+\t/ {
            split($0, f, "\t")
            if (f[1] != "-" && f[2] != "-") {
                adds += f[1]; dels += f[2]
            }
            files++
        }
        END {
            if (sha != "") {
                printf "%s,%s,%s,\"%s\",%d,%d,%d,%d\n",
                    repo, sha, date, author, files, adds, dels, adds-dels
            }
        }'
done
