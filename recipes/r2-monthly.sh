#!/bin/bash
# Optional: monthly encrypted snapshot of the *bare* git archive → S3-compatible
# storage (Cloudflare R2, AWS S3, …).
#
# This is NOT the daily backup. Daily protection is `annals backup`
# pushing to a git remote. This recipe is a second copy of the already-
# compressed git object store, for when the git remote itself dies.
#
# Runs well on the machine that holds the bare repo (often a small VPS).
# Do not pull a 1 GB archive over a residential uplink just to verify it —
# `aws s3api head-object` + the first 100 bytes (GPG packet 0x8c) is enough
# locally; full decrypt belongs next to the object store.
#
# Setup:
#   aws configure --profile r2
#   printf '%s' 'PASSPHRASE' > ~/.backup-gpg.pass && chmod 600 ~/.backup-gpg.pass
#   export R2_BUCKET=… R2_ACCOUNT_ID=… PASSPHRASE_FILE=~/.backup-gpg.pass
#   export REPO=$HOME/git/annals-archive.git
set -euo pipefail

: "${R2_BUCKET:?}" "${R2_ACCOUNT_ID:?}" "${PASSPHRASE_FILE:?}"
AWS_PROFILE_NAME=${AWS_PROFILE_NAME:-r2}
REPO=${REPO:?set REPO to the bare git repo}
KEEP=${KEEP:-3}
R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
STAMP=$(date +%Y%m)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

log() { echo "[$(date '+%F %T')] $*"; }

[[ -d $REPO ]] || { log "FAIL repo not found: $REPO"; exit 1; }

log "repacking $(basename "$REPO") ($(du -sh "$REPO" | cut -f1))"
git -C "$REPO" -c pack.windowMemory=64m -c pack.packSizeLimit=256m \
    gc --quiet --aggressive --prune=now 2>/dev/null || log "gc had warnings, continuing"
log "after repack: $(du -sh "$REPO" | cut -f1)"

git -C "$REPO" fsck --no-progress --no-dangling >/dev/null \
  || log "WARN fsck reported issues"

name="annals-$STAMP.tar.gz"
tar -czf "$WORK/$name" -C "$(dirname "$REPO")" "$(basename "$REPO")"
gpg --batch --yes --quiet --passphrase-file "$PASSPHRASE_FILE" \
    --symmetric --cipher-algo AES256 -o "$WORK/$name.gpg" "$WORK/$name"
rm -f "$WORK/$name"

aws s3 cp --quiet "$WORK/$name.gpg" "s3://$R2_BUCKET/annals-git/$name.gpg" \
  --profile "$AWS_PROFILE_NAME" --endpoint-url "$R2_ENDPOINT"
log "uploaded annals-git/$name.gpg ($(du -h "$WORK/$name.gpg" | cut -f1))"

# Keep the newest KEEP archives.
mapfile -t keys < <(aws s3 ls "s3://$R2_BUCKET/annals-git/" \
                    --profile "$AWS_PROFILE_NAME" --endpoint-url "$R2_ENDPOINT" \
                    2>/dev/null | sort | awk '{print $4}')
if (( ${#keys[@]} > KEEP )); then
  for k in "${keys[@]:0:${#keys[@]}-KEEP}"; do
    aws s3 rm --quiet "s3://$R2_BUCKET/annals-git/$k" \
      --profile "$AWS_PROFILE_NAME" --endpoint-url "$R2_ENDPOINT" \
      && log "pruned $k"
  done
fi
log "done"
