#!/usr/bin/env bash
# Wait for the local API health endpoint and preserve startup evidence on failure.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
API_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly API_DIR
readonly API_URL="${WAIT_FOR_API_URL:-http://localhost:8080/health}"
readonly MAX_WAIT_TIME="${WAIT_FOR_API_TIMEOUT_SECONDS:-800}"
readonly INTERVAL="${WAIT_FOR_API_INTERVAL_SECONDS:-5}"
readonly CURL_CONNECT_TIMEOUT="${WAIT_FOR_API_CURL_CONNECT_TIMEOUT_SECONDS:-5}"
readonly CURL_MAX_TIME="${WAIT_FOR_API_CURL_MAX_TIME_SECONDS:-10}"

if [[ "$#" -ne 0 ]]; then
  echo "ERROR: wait-for-api.sh accepts no arguments; configure it with WAIT_FOR_API_* environment variables." >&2
  echo "Usage: wait-for-api.sh" >&2
  exit 2
fi

BODY_FILE="$(mktemp)"
CURL_ERROR_FILE="$(mktemp)"
FAILURE_REPORTED=0
LAST_CURL_EXIT=0
LAST_HTTP_STATUS=000
START_TIME="$(date +%s)"

cleanup() {
  rm -f "$BODY_FILE" "$CURL_ERROR_FILE"
}

docker_compose() {
  (cd "$API_DIR" && docker compose "$@")
}

emit_container_diagnostics() {
  local container_id

  echo "API startup diagnostics:" >&2
  docker_compose ps -a >&2 || true

  container_id="$(docker_compose ps -aq grants-api 2>/dev/null | head -n 1)"
  if [[ -n "$container_id" ]]; then
    docker inspect --format \
      'State={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{json .State.Error}}' \
      "$container_id" >&2 || true
  else
    echo "No grants-api container exists." >&2
  fi

  echo "Last 300 grants-api log lines:" >&2
  docker_compose logs --no-color --tail 300 grants-api >&2 || true
}

emit_failure() {
  local reason="$1"
  local elapsed="$2"

  FAILURE_REPORTED=1
  printf 'status: failed\nreason: "%s"\nelapsed_seconds: %s\ncurl_exit: %s\nhttp_status: %s\n' \
    "$reason" "$elapsed" "$LAST_CURL_EXIT" "$LAST_HTTP_STATUS"
  echo "ERROR: API did not become ready: $reason." >&2
  if [[ -s "$CURL_ERROR_FILE" ]]; then
    echo "Last curl error:" >&2
    head -c 4096 "$CURL_ERROR_FILE" >&2
    echo >&2
  fi
  if [[ -s "$BODY_FILE" ]]; then
    echo "Last health response body (up to 4096 bytes):" >&2
    head -c 4096 "$BODY_FILE" >&2
    echo >&2
  fi
  emit_container_diagnostics
  exit 1
}

on_exit() {
  local status=$?
  if [[ "$status" -ne 0 && "$FAILURE_REPORTED" -eq 0 ]]; then
    local now elapsed
    now="$(date +%s)"
    elapsed=$((now - START_TIME))
    printf 'status: failed\nreason: "unexpected-command-failure"\nelapsed_seconds: %s\n' "$elapsed"
    echo "ERROR: API readiness check stopped unexpectedly." >&2
    emit_container_diagnostics
  fi
  cleanup
}
trap on_exit EXIT

require_nonnegative_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    FAILURE_REPORTED=1
    echo "ERROR: $name must be a non-negative integer; received '$value'." >&2
    exit 2
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    FAILURE_REPORTED=1
    echo "ERROR: $name must be a positive integer; received '$value'." >&2
    exit 2
  fi
}

require_nonnegative_integer WAIT_FOR_API_TIMEOUT_SECONDS "$MAX_WAIT_TIME"
require_positive_integer WAIT_FOR_API_INTERVAL_SECONDS "$INTERVAL"
require_positive_integer WAIT_FOR_API_CURL_CONNECT_TIMEOUT_SECONDS "$CURL_CONNECT_TIMEOUT"
require_positive_integer WAIT_FOR_API_CURL_MAX_TIME_SECONDS "$CURL_MAX_TIME"

echo "Waiting up to ${MAX_WAIT_TIME}s for GET ${API_URL}." >&2

while true; do
  now="$(date +%s)"
  elapsed=$((now - START_TIME))
  if [[ "$elapsed" -ge "$MAX_WAIT_TIME" ]]; then
    emit_failure "timeout" "$elapsed"
  fi

  running_services="$(docker_compose ps --status running --services grants-api 2>/dev/null || true)"
  if ! grep -Fxq grants-api <<<"$running_services"; then
    emit_failure "grants-api container is not running" "$elapsed"
  fi

  : >"$BODY_FILE"
  : >"$CURL_ERROR_FILE"
  remaining=$((MAX_WAIT_TIME - elapsed))
  attempt_max_time="$CURL_MAX_TIME"
  if [[ "$attempt_max_time" -gt "$remaining" ]]; then
    attempt_max_time="$remaining"
  fi
  attempt_connect_timeout="$CURL_CONNECT_TIMEOUT"
  if [[ "$attempt_connect_timeout" -gt "$attempt_max_time" ]]; then
    attempt_connect_timeout="$attempt_max_time"
  fi
  set +e
  LAST_HTTP_STATUS="$(curl \
    --silent \
    --show-error \
    --request GET \
    --output "$BODY_FILE" \
    --write-out '%{http_code}' \
    --connect-timeout "$attempt_connect_timeout" \
    --max-time "$attempt_max_time" \
    "$API_URL" 2>"$CURL_ERROR_FILE")"
  LAST_CURL_EXIT=$?
  set -e

  now="$(date +%s)"
  elapsed=$((now - START_TIME))
  if [[ "$LAST_CURL_EXIT" -eq 0 && "$LAST_HTTP_STATUS" =~ ^2[0-9][0-9]$ && "$elapsed" -lt "$MAX_WAIT_TIME" ]]; then
    printf 'status: ready\nelapsed_seconds: %s\nhttp_status: %s\n' "$elapsed" "$LAST_HTTP_STATUS"
    exit 0
  fi

  if [[ "$elapsed" -ge "$MAX_WAIT_TIME" ]]; then
    emit_failure "timeout" "$elapsed"
  fi

  remaining=$((MAX_WAIT_TIME - elapsed))
  sleep_for="$INTERVAL"
  if [[ "$sleep_for" -gt "$remaining" ]]; then
    sleep_for="$remaining"
  fi
  echo "API not ready (curl=$LAST_CURL_EXIT http=$LAST_HTTP_STATUS); retrying in ${sleep_for}s." >&2
  sleep "$sleep_for"
done
