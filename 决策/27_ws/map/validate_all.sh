#!/usr/bin/env bash

set -uo pipefail

SETUP="${HOME}/.ros/decision_27_ws_nav2/install/setup.bash"
if [[ ! -f "${SETUP}" ]]; then
  echo "Workspace is not built. Run: bash map/build_simulation.sh" >&2
  exit 1
fi

set +u
source "${SETUP}"
set -u

# Gazebo Sim can outlive ros2 launch briefly while its server is shutting down.
# Remove only processes belonging to this simulation world so that a stale
# /clock cannot interfere with the next scenario.
cleanup_sim_world() {
  local pids
  pids="$(pgrep -f 'gz sim.*rm_arena\.sdf' || true)"
  if [[ -n "${pids}" ]]; then
    kill -TERM ${pids} 2>/dev/null || true
    sleep 1
    pids="$(pgrep -f 'gz sim.*rm_arena\.sdf' || true)"
    [[ -z "${pids}" ]] || kill -KILL ${pids} 2>/dev/null || true
  fi
}

cleanup_sim_world
trap cleanup_sim_world EXIT

for package in nav2_controller nav2_navfn_planner; do
  if ! ros2 pkg prefix "${package}" >/dev/null 2>&1; then
    echo "Nav2 is missing. Install it first:" >&2
    echo "sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup" >&2
    exit 2
  fi
done

scenarios=(return_home posture attack_outpost no_ammo dodge)
passed=0

for scenario in "${scenarios[@]}"; do
  log_file="$(mktemp "/tmp/rm_${scenario}.XXXXXX.log")"
  echo "[RUN] ${scenario}"
  timeout 100s ros2 launch rm_decision_sim simulation.launch.py \
    scenario:="${scenario}" gazebo_gui:=false rviz:=false exit_on_result:=true \
    >"${log_file}" 2>&1
  launch_status=$?

  if rg -q "VALIDATION PASS \[${scenario}\]" "${log_file}"; then
    detail="$(rg "VALIDATION PASS \[${scenario}\]" "${log_file}" | tail -1)"
    echo "[PASS] ${detail#*: }"
    passed=$((passed + 1))
  else
    echo "[FAIL] ${scenario} (launch status ${launch_status}, log ${log_file})" >&2
    tail -40 "${log_file}" >&2
  fi
  cleanup_sim_world
  sleep 2
done

echo "Result: ${passed}/${#scenarios[@]} scenarios passed"
[[ "${passed}" -eq "${#scenarios[@]}" ]]
