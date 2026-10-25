#!/usr/bin/env bash
set -euo pipefail

python -m rl.cli.evaluate "$@" --stochastic

