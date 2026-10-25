"""旧入口兼容层。

实际实现位于 :mod:`rm2026_sim.app` 包中。保留本文件是为了兼容已有脚本和
测试里的 ``from rm2026_sim.app import SimulatorApp``，新代码建议按职责导入
``rm2026_sim.app.main`` 或对应的 mixin 模块。
"""

from .app.main import (
    APP_ROOT,
    MAP_PATH,
    FIELD_LAYOUT_PATH,
    SNAPSHOT_PATH,
    MAP_GEOMETRY_PATH,
    WINDOW_SIZE,
    STATIC_COLLISION_RECTANGLES,
    SimulatorApp,
    main,
)

__all__ = [
    "APP_ROOT",
    "MAP_PATH",
    "FIELD_LAYOUT_PATH",
    "SNAPSHOT_PATH",
    "MAP_GEOMETRY_PATH",
    "WINDOW_SIZE",
    "STATIC_COLLISION_RECTANGLES",
    "SimulatorApp",
    "main",
]
