#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
API_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
readonly API_DIR
readonly WAIT_SCRIPT="$API_DIR/bin/wait-for-api.sh"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

pass_count=0

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  local file="$1"
  local expected="$2"
  grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_exists() {
  local file="$1"
  [[ ! -e "$file" ]] || fail "did not expect $file to exist"
}

make_fake_commands() {
  local case_dir="$1"
  mkdir -p "$case_dir/bin"

  cat >"$case_dir/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >>"$FAKE_DOCKER_CALLS"

if [[ "$*" == "compose ps --status running --services grants-api" ]]; then
  if [[ "$DOCKER_SCENARIO" != "stopped" ]]; then
    echo grants-api
  fi
elif [[ "$*" == "compose ps -a" ]]; then
  echo "NAME STATUS"
  echo "grants-api Exited (137)"
elif [[ "$*" == "compose ps -aq grants-api" ]]; then
  echo fake-container-id
elif [[ "$1" == "inspect" ]]; then
  echo 'State=exited ExitCode=137 OOMKilled=true Error="out of memory"'
elif [[ "$1 $2" == "compose logs" ]]; then
  echo "bounded grants-api log evidence"
else
  echo "unexpected docker invocation: $*" >&2
  exit 99
fi
EOF

  cat >"$case_dir/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -eu
printf 'called\n' >>"$FAKE_CURL_CALLS"
printf '%s\n' "$*" >>"$FAKE_CURL_ARGS"

output_file=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "--output" ]]; then
    output_file="$2"
    shift 2
  else
    shift
  fi
done

if [[ "$CURL_SCENARIO" == "slow_ready" ]]; then
  sleep 1
  printf '{"status":"ready"}' >"$output_file"
  printf '200'
elif [[ "$CURL_SCENARIO" == "ready" ]]; then
  printf '{"status":"ready"}' >"$output_file"
  printf '200'
else
  printf '{"status":"starting"}' >"$output_file"
  printf '503'
fi
EOF

  chmod +x "$case_dir/bin/docker" "$case_dir/bin/curl"
}

run_case() {
  local name="$1"
  local docker_scenario="$2"
  local curl_scenario="$3"
  local timeout="$4"
  local interval="$5"
  local case_dir="$TEST_ROOT/$name"

  mkdir -p "$case_dir"
  make_fake_commands "$case_dir"

  set +e
  PATH="$case_dir/bin:$PATH" \
    DOCKER_SCENARIO="$docker_scenario" \
    CURL_SCENARIO="$curl_scenario" \
    FAKE_DOCKER_CALLS="$case_dir/docker-calls" \
    FAKE_CURL_CALLS="$case_dir/curl-calls" \
    FAKE_CURL_ARGS="$case_dir/curl-args" \
    WAIT_FOR_API_TIMEOUT_SECONDS="$timeout" \
    WAIT_FOR_API_INTERVAL_SECONDS="$interval" \
    "$WAIT_SCRIPT" >"$case_dir/stdout" 2>"$case_dir/stderr"
  CASE_STATUS=$?
  set -e

  CASE_DIR="$case_dir"
}

run_case ready running ready 5 1
[[ "$CASE_STATUS" -eq 0 ]] || fail "ready case exited $CASE_STATUS"
assert_contains "$CASE_DIR/stdout" "status: ready"
assert_contains "$CASE_DIR/stdout" "http_status: 200"
pass_count=$((pass_count + 1))

run_case stopped stopped unavailable 5 1
[[ "$CASE_STATUS" -eq 1 ]] || fail "stopped case exited $CASE_STATUS"
assert_contains "$CASE_DIR/stdout" 'reason: "grants-api container is not running"'
assert_contains "$CASE_DIR/stderr" "State=exited ExitCode=137 OOMKilled=true"
assert_contains "$CASE_DIR/stderr" "bounded grants-api log evidence"
assert_not_exists "$CASE_DIR/curl-calls"
pass_count=$((pass_count + 1))

run_case service_unavailable running unavailable 1 1
[[ "$CASE_STATUS" -eq 1 ]] || fail "503 case exited $CASE_STATUS"
assert_contains "$CASE_DIR/stdout" 'reason: "timeout"'
assert_contains "$CASE_DIR/stdout" "http_status: 503"
assert_contains "$CASE_DIR/stderr" '{"status":"starting"}'
pass_count=$((pass_count + 1))

boundary_start="$(date +%s)"
run_case exact_boundary running unavailable 1 1
boundary_elapsed=$(($(date +%s) - boundary_start))
[[ "$CASE_STATUS" -eq 1 ]] || fail "boundary case exited $CASE_STATUS"
[[ "$boundary_elapsed" -ge 1 && "$boundary_elapsed" -lt 3 ]] || \
  fail "boundary case took ${boundary_elapsed}s"
boundary_probe_count="$(wc -l <"$CASE_DIR/curl-calls" | tr -d ' ')"
[[ "$boundary_probe_count" -eq 1 ]] || \
  fail "boundary case probed again at or after the deadline"
pass_count=$((pass_count + 1))

run_case late_success running slow_ready 1 1
[[ "$CASE_STATUS" -eq 1 ]] || fail "late success case exited $CASE_STATUS"
assert_contains "$CASE_DIR/stdout" 'reason: "timeout"'
assert_contains "$CASE_DIR/stdout" "http_status: 200"
assert_contains "$CASE_DIR/curl-args" "--connect-timeout 1 --max-time 1"
assert_contains "$CASE_DIR/docker-calls" "compose ps -a"
pass_count=$((pass_count + 1))

unknown_dir="$TEST_ROOT/unknown_argument"
mkdir -p "$unknown_dir"
set +e
"$WAIT_SCRIPT" --unknown >"$unknown_dir/stdout" 2>"$unknown_dir/stderr"
unknown_status=$?
set -e
[[ "$unknown_status" -eq 2 ]] || fail "unknown argument case exited $unknown_status"
assert_contains "$unknown_dir/stderr" "accepts no arguments"
assert_contains "$unknown_dir/stderr" "Usage: wait-for-api.sh"
pass_count=$((pass_count + 1))

echo "PASS: $pass_count wait-for-api shell tests"
