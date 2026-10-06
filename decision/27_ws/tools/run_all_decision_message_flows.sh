#!/usr/bin/env bash

# 一次构建，按任务优先级顺序依次运行全部消息端测试。
# 所有测试使用相同话题，因此必须串行执行，不能同时发布模拟输入。
set -eo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "========== 消息端任务 1～9 总测试开始 =========="
for scenario in return_home attack_outpost no_ammo dodge patrol spin_control gimbal_control low_health_recovery health_threshold_parameter; do
  echo
  echo "---------- 启动 ${scenario} ----------"
  bash "${SCRIPT_DIR}/run_decision_message_flow.sh" "${scenario}"
  export DECISION_MESSAGE_FLOW_SKIP_BUILD=1
done
echo
echo "========== 消息端任务 1～9 总测试完成 =========="
