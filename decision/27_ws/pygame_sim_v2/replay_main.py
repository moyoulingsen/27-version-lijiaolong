#!/usr/bin/env python3
"""Compatibility entry point for the SQLite replay in SimulatorApp."""

import sys


if __name__ == "__main__":
    from rm2026_sim.app import main as simulator_main

    simulator_main(["--replay", *sys.argv[1:]])
