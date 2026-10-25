"""RMUC 2026 Pygame 应用模块。

``main.py`` 负责组装应用对象；其它文件按运行时职责拆分，避免所有界面和
仿真代码继续堆在单个文件中。
"""

# 保留旧模块曾经暴露的常量，避免外部脚本因目录化而失效。
from .main import *
from .main import (
    APP_ROOT,
    FIELD_LAYOUT_PATH,
    MAP_GEOMETRY_PATH,
    MAP_PATH,
    SNAPSHOT_PATH,
    STATIC_COLLISION_RECTANGLES,
    WINDOW_SIZE,
    SimulatorApp,
    main,
)

__all__ = [
    "APP_ROOT",
    "FIELD_LAYOUT_PATH",
    "MAP_GEOMETRY_PATH",
    "MAP_PATH",
    "SNAPSHOT_PATH",
    "STATIC_COLLISION_RECTANGLES",
    "WINDOW_SIZE",
    "SimulatorApp",
    "main",
]
