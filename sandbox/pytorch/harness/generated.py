"""Load the coding agent's model.py and loss.py, checked by the allowlist before they are imported.

This is the load-time half of the "checked twice" contract: the worker runs the same checker before
a job starts, and the harness runs it again here, by source, as the last check before the code
executes. Each error raised carries the results.json error_code the executor reports.
"""

from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path

from torch import nn

from harness.codecheck import Finding, check_module

# Unique module names so loading model.py and loss.py never collide in sys.modules.
_names = itertools.count()


class GeneratedCodeError(Exception):
    """Base for failures in generated code; error_code is what results.json reports."""

    error_code = "train.error"


class CodeRefused(GeneratedCodeError):
    """The allowlist checker rejected the source. The findings are listed in results.json."""

    error_code = "code.refused"

    def __init__(self, filename: str, findings: list[Finding]) -> None:
        self.findings = findings
        detail = "; ".join(f"{f.code} line {f.line}: {f.message}" for f in findings)
        super().__init__(f"{filename} refused by the allowlist: {detail}")


class CodeTooLarge(CodeRefused):
    """The source is larger than the checker's byte limit."""

    error_code = "code.too_large"


class ModelTooLarge(GeneratedCodeError):
    """The model has more parameters than limits.MAX_PARAMS."""

    error_code = "code.too_large"


class CodeImportFailed(GeneratedCodeError):
    """The source passed the checker but could not be imported or did not define the class."""

    error_code = "code.import_failed"


class ShapeMismatch(GeneratedCodeError):
    """The model's prediction shape does not match the target's."""

    error_code = "code.shape_mismatch"


def load_generated_model(code_dir: Path, kwargs: dict[str, object]) -> nn.Module:
    """Build ``Model`` from ``code_dir/model.py`` with the config kwargs."""
    model_class = _load_class(code_dir, "model.py", "Model")
    try:
        return model_class(**kwargs)
    except Exception as exc:
        raise CodeImportFailed(f"Model(**kwargs) raised {type(exc).__name__}: {exc}") from exc


def load_generated_loss(code_dir: Path) -> nn.Module:
    """Build ``Loss`` from ``code_dir/loss.py``; its forward is (prediction, target, valid_mask)."""
    loss_class = _load_class(code_dir, "loss.py", "Loss")
    try:
        return loss_class()
    except Exception as exc:
        raise CodeImportFailed(f"Loss() raised {type(exc).__name__}: {exc}") from exc


def _load_class(code_dir: Path, filename: str, symbol: str) -> type[nn.Module]:
    path = code_dir / filename
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CodeImportFailed(f"Cannot read {path}: {exc}") from exc

    findings = check_module(source, filename=filename)
    if findings:
        if any(finding.code == "check.too_large" for finding in findings):
            raise CodeTooLarge(filename, findings)
        raise CodeRefused(filename, findings)

    spec = importlib.util.spec_from_file_location(f"arp_generated_{next(_names)}", path)
    if spec is None or spec.loader is None:
        raise CodeImportFailed(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise CodeImportFailed(f"{filename} raised {type(exc).__name__} on import: {exc}") from exc

    obj = module.__dict__.get(symbol)
    if obj is None:
        raise CodeImportFailed(f"{filename} does not define '{symbol}'")
    if not (isinstance(obj, type) and issubclass(obj, nn.Module)):
        raise CodeImportFailed(f"{filename}:{symbol} must be a torch.nn.Module subclass")
    return obj
