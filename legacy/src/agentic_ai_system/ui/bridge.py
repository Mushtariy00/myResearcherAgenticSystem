from __future__ import annotations

import queue
import threading
from typing import Any


approval_event = threading.Event()
approval_decision: dict[str, bool] = {"approved": False}
ui_update_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()


def clear_ui_queue() -> None:
    while True:
        try:
            ui_update_queue.get_nowait()
        except queue.Empty:
            break

