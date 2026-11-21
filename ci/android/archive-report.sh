#!/usr/bin/env bash
# Append one report to gh-pages using only fast-forward pushes.
set -euo pipefail
SOURCE=$(cd -- "$1" && pwd)
KEY=${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}
[[ "$KEY" =~ ^[0-9]+-[0-9]+$ ]]
[[ -s "$SOURCE/report.json" && -s "$SOURCE/index.html" ]]
ROOT=$(git rev-parse --show-toplevel)
SITE=$(mktemp -d "${RUNNER_TEMP:-/tmp}/screenshot-site.XXXXXX")
cleanup() { git -C "$ROOT" worktree remove --force "$SITE" 2>/dev/null || rmdir "$SITE"; }
trap cleanup EXIT
REF=refs/heads/gh-pages
export GIT_AUTHOR_NAME='github-actions[bot]' GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
for trial in 1 2 3 4 5; do
    if git ls-remote --exit-code origin "$REF" >/dev/null; then
        git fetch --no-tags origin "$REF"
        BASE=$(git rev-parse FETCH_HEAD)
    else
        CODE=$?
        if [[ $CODE != 2 ]]; then exit "$CODE"; fi
        TREE=$(git mktree </dev/null)
        BASE=$(git commit-tree "$TREE" -m 'Initialize screenshot report archive')
    fi
    if [[ $trial == 1 ]]; then
        git worktree add --detach "$SITE" "$BASE"
    else
        git -C "$SITE" reset --hard "$BASE"
    fi
    [[ ! -L "$SITE/runs" ]]
    DEST="$SITE/runs/$KEY"
    if [[ -e "$DEST" ]]; then
        echo "Report $KEY already archived."
        exit 0
    fi
    mkdir -p "$DEST"
    for FILE in index.html report.json reference.png actual.png diff.png; do
        if [[ -f "$SOURCE/$FILE" && ! -L "$SOURCE/$FILE" ]]; then cp "$SOURCE/$FILE" "$DEST/$FILE"; fi
    done
    python3 "$ROOT/ci/android/report.py" index --site "$SITE"
    git -C "$SITE" add -- .nojekyll index.html "runs/$KEY"
    git -C "$SITE" commit -m "Archive screenshot report $KEY"
    if git -C "$SITE" push origin "HEAD:$REF"; then exit 0; fi
    sleep "$trial"
done
exit 1
