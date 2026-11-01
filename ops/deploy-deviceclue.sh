#!/usr/bin/env bash
set -euo pipefail
: "${SITE_IMAGE:?Set SITE_IMAGE}"
: "${EXPECTED_DEPLOY_COMMIT:?Set EXPECTED_DEPLOY_COMMIT}"
[[ "$SITE_IMAGE" == seo-deviceclue:* ]] || { echo 'Unexpected image namespace' >&2; exit 1; }
[[ "$EXPECTED_DEPLOY_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'Expected full commit SHA' >&2; exit 1; }
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
deploy_dir=/opt/seo-sites/deviceclue
compose_file="$deploy_dir/docker-compose.yml"
test -w "$deploy_dir"
exec 9>"$deploy_dir/deploy.lock"
flock -w 300 9
docker image inspect "$SITE_IMAGE" >/dev/null

candidate="seo-deviceclue-check-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}"
cleanup_candidate() { docker rm -f "$candidate" >/dev/null 2>&1 || true; }
trap cleanup_candidate EXIT
docker run -d --name "$candidate" --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 --memory 512m -p 127.0.0.1::3000 "$SITE_IMAGE" >/dev/null
candidate_port=$(docker inspect -f '{{(index (index .NetworkSettings.Ports "3000/tcp") 0).HostPort}}' "$candidate")
ready() {
  local url=$1
  for attempt in $(seq 1 30); do
    if curl --fail --silent --max-time 3 "$url/api/health" >/dev/null; then return 0; fi
    sleep 2
  done
  return 1
}
ready "http://127.0.0.1:$candidate_port"
SITE_TEST_URL="http://127.0.0.1:$candidate_port" node "$repo_root/sites/deviceclue/scripts/smoke.mjs"
cleanup_candidate
trap - EXIT

previous_image=$(docker inspect -f '{{.Image}}' seo-deviceclue 2>/dev/null || true)
previous_compose=$(mktemp "$deploy_dir/compose-backup.XXXXXX")
if [[ -f "$compose_file" ]]; then cp "$compose_file" "$previous_compose"; fi
compose() { docker compose -p seo-deviceclue -f "$compose_file" "$@"; }
rollback() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo 'DeviceClue deployment failed; restoring previous release.' >&2
    docker logs seo-deviceclue --tail=40 || true
    if [[ -s "$previous_compose" ]]; then cp "$previous_compose" "$compose_file"; fi
    if [[ -n "$previous_image" ]]; then
      SITE_IMAGE="$previous_image" compose up -d --no-build --pull never || true
    else
      compose stop deviceclue || true
    fi
  fi
  rm -f -- "$previous_compose"
  exit "$status"
}
trap rollback EXIT
install -m 644 "$repo_root/ops/docker-compose.deviceclue.yml" "$compose_file"
compose up -d --no-build --pull never
ready http://127.0.0.1:5006
SITE_TEST_URL=http://127.0.0.1:5006 node "$repo_root/sites/deviceclue/scripts/smoke.mjs"
docker tag "$SITE_IMAGE" seo-deviceclue:latest
printf '%s\n' "$EXPECTED_DEPLOY_COMMIT" > "$deploy_dir/deployed-commit"
echo "Verified DeviceClue at $EXPECTED_DEPLOY_COMMIT"
