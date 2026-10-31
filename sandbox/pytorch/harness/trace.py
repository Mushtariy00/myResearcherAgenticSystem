"""Each module's input and output shapes in one forward pass, for the report of a pass that
failed: the coding agent's repair then sees where the shapes went wrong, not only the traceback.

    with ShapeTrace(model) as trace:
        prediction = model(images)  # on an exception, trace.report() says where and with what
"""

from __future__ import annotations

from collections import deque
from types import TracebackType
from typing import Any

import torch
from torch import nn

KEEP = 16  # the last modules that ran, in the report
MAX_ITEMS = 6  # of a list or a tuple, in a shape


def shape_of(value: Any) -> str:
    """A value as the trace shows it: a tensor's shape, a list or tuple of them, else its type."""
    if isinstance(value, torch.Tensor):
        return str(tuple(value.shape))
    if isinstance(value, list | tuple):
        items = [shape_of(item) for item in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            items.append(f"... {len(value)} in all")
        return f"[{', '.join(items)}]"
    if isinstance(value, dict):
        items = [f"{key}: {shape_of(item)}" for key, item in list(value.items())[:MAX_ITEMS]]
        return "{" + ", ".join(items) + "}"
    if value is None or isinstance(value, bool | int | float):
        return repr(value)
    return type(value).__name__


class ShapeTrace:
    """Forward hooks on every module of ``model`` while the ``with`` block runs. ``report()``
    names the modules whose forward was running when the pass failed, outermost first, with the
    inputs of the innermost, then the last modules that ran to the end, with their inputs and
    outputs."""

    def __init__(self, model: nn.Module, keep: int = KEEP) -> None:
        self.model = model
        self.names = {module: name or "Model" for name, module in model.named_modules()}
        self.running: list[tuple[str, str]] = []  # (module, its inputs) whose forward is running
        self.finished: deque[str] = deque(maxlen=keep)
        self.handles: list[torch.utils.hooks.RemovableHandle] = []

    def __enter__(self) -> ShapeTrace:
        for module in self.names:
            self.handles.append(module.register_forward_pre_hook(self.entered))
            self.handles.append(module.register_forward_hook(self.left))
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for handle in self.handles:
            handle.remove()
        self.handles.clear()

    def label(self, module: nn.Module) -> str:
        return f"{self.names.get(module, '?')} ({type(module).__name__})"

    def entered(self, module: nn.Module, args: tuple[Any, ...]) -> None:
        inputs = ", ".join(shape_of(arg) for arg in args[:MAX_ITEMS]) or "nothing"
        self.running.append((self.label(module), inputs))

    def left(self, module: nn.Module, args: tuple[Any, ...], output: Any) -> None:
        label, inputs = self.running.pop() if self.running else (self.label(module), "?")
        self.finished.append(f"{label}: {inputs} -> {shape_of(output)}")

    def report(self) -> str:
        lines: list[str] = []
        if self.running:
            lines.append(
                "The forward pass failed inside: " + " > ".join(label for label, _ in self.running)
            )
            lines.append(f"whose inputs were: {self.running[-1][1]}")
        if self.finished:
            lines.append("The last modules that ran to the end (inputs -> outputs):")
            lines += [f"  {line}" for line in self.finished]
        return "\n".join(lines)
