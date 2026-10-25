#!/usr/bin/env bash
set -euo pipefail

python -m rl.cli.train --backend gpu --device cuda --curriculum "$@"

