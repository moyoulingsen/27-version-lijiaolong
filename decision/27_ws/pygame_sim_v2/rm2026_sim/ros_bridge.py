"""UDP client for the external ROS 2/BehaviorTree.CPP bridge."""

from __future__ import annotations

import json
import socket
import time
from typing import Any


class BehaviorTreeBridgeClient:
    """Exchange simulator state and decisions without importing rclpy."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 39001,
        timeout: float = 1.0,
    ) -> None:
        self._address = (host, port)
        self._timeout = timeout
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((host, 0))
        self._socket.setblocking(False)
        self._latest: dict[str, Any] | None = None
        self._last_received = 0.0

    @property
    def connected(self) -> bool:
        return time.monotonic() - self._last_received <= self._timeout

    def publish_state(self, state: dict[str, Any]) -> None:
        try:
            payload = json.dumps(state, separators=(",", ":")).encode("utf-8")
            self._socket.sendto(payload, self._address)
        except OSError:
            return
        while True:
            try:
                data, _ = self._socket.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError:
                return
            try:
                output = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(output, dict):
                self._latest = output
                self._last_received = time.monotonic()

    def latest_output(self) -> dict[str, Any] | None:
        return self._latest if self.connected else None

    def clear_output(self) -> None:
        self._latest = None
        self._last_received = 0.0

    def close(self) -> None:
        self._socket.close()
