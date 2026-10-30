"""Allowlist checker for coding-agent source, run before any generated module is imported.

This is the static half of the "checked twice" contract (docs/design/experiments.md): the worker
runs it before a smoke job, and the harness runs it again at load time inside the sandbox. It is an
allowlist, so anything not explicitly permitted is refused with a finding. The sandbox (no network,
read-only root, no secrets) is the last line of defence, never the first.

This file has an identical twin at sandbox/pytorch/harness/codecheck.py, because the sandbox image
cannot import packages/core. A test keeps the two byte-for-byte equal; edit both together. It
depends only on the standard library for the same reason.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass

MAX_SOURCE_BYTES = 20_000

# Modules the coding agent may import, plain or from-imports (docs/design/experiments.md).
ALLOWED_IMPORTS = frozenset(
    {
        "torch",
        "torch.nn",
        "torch.nn.functional",
        "math",
        "typing",
        "dataclasses",
        "functools",
        "collections",
        "__future__",
    }
)

# Builtins the agent may name. Everything else that is a builtin (open, exec, eval, compile,
# __import__, globals, vars, input, ...) is refused by the allowlist.
SAFE_BUILTINS = frozenset(
    {
        "range",
        "len",
        "int",
        "float",
        "bool",
        "str",
        "tuple",
        "list",
        "dict",
        "set",
        "frozenset",
        "min",
        "max",
        "abs",
        "sum",
        "round",
        "zip",
        "enumerate",
        "reversed",
        "sorted",
        "any",
        "all",
        "isinstance",
        "issubclass",
        "super",
        "print",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "NotImplementedError",
        "IndexError",
        "KeyError",
    }
)

# torch entry points for file I/O, native extensions and new processes: refused even though torch
# itself is allowed. A full dotted path is refused when it starts with one of these prefixes.
TORCH_DENYLIST = frozenset(
    {
        "torch.load",
        "torch.save",
        "torch.from_file",
        "torch.serialization",
        "torch.Storage",
        "torch.TypedStorage",
        "torch.UntypedStorage",
        "torch.hub",
        "torch.jit",
        "torch.utils",
        "torch.ops",
        "torch.classes",
        "torch.multiprocessing",
        "torch.distributed",
    }
)

# Builtins that reach attributes by name and so sidestep the static attribute checks.
REFLECTION_BUILTINS = frozenset({"getattr", "setattr", "delattr", "hasattr"})

_BUILTIN_NAMES = frozenset(dir(builtins))


@dataclass(frozen=True)
class Finding:
    """One reason a module was refused, at a 1-based source line."""

    line: int
    code: str
    message: str


def check_module(source: str, *, filename: str) -> list[Finding]:
    """Return the reasons ``source`` is refused; an empty list means it is allowed."""
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return [
            Finding(1, "check.too_large", f"{filename} is larger than {MAX_SOURCE_BYTES} bytes")
        ]
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [Finding(exc.lineno or 1, "check.syntax", f"{filename} does not parse: {exc.msg}")]

    findings: list[Finding] = []
    findings += _check_top_level(tree)
    aliases = _torch_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            findings += _check_import(node)
        elif isinstance(node, ast.Call):
            findings += _check_call(node)
        elif isinstance(node, ast.Name):
            findings += _check_name(node)
        elif isinstance(node, ast.Attribute):
            findings += _check_attribute(node, aliases)
    return sorted(findings, key=lambda f: (f.line, f.code))


def _check_top_level(tree: ast.Module) -> list[Finding]:
    """At module level only imports, defs, constant assignments and a docstring are allowed."""
    findings: list[Finding] = []
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Import | ast.ImportFrom | ast.ClassDef):
            continue
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if index == 0 and _is_docstring(node):
            continue
        if isinstance(node, ast.Assign | ast.AnnAssign) and _is_constant(node.value):
            continue
        findings.append(
            Finding(
                node.lineno,
                "check.top_level",
                "Only imports, definitions and constants are allowed at module level",
            )
        )
    return findings


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_constant(value: ast.expr | None) -> bool:
    """True for a literal, or a container, unary or binary expression built only from literals."""
    if value is None:
        return False
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, ast.Tuple | ast.List | ast.Set):
        return all(_is_constant(element) for element in value.elts)
    if isinstance(value, ast.Dict):
        return all(_is_constant(key) for key in value.keys if key is not None) and all(
            _is_constant(item) for item in value.values
        )
    if isinstance(value, ast.UnaryOp):
        return _is_constant(value.operand)
    if isinstance(value, ast.BinOp):
        return _is_constant(value.left) and _is_constant(value.right)
    return False


def _check_import(node: ast.Import | ast.ImportFrom) -> list[Finding]:
    if isinstance(node, ast.Import):
        return [
            Finding(node.lineno, "check.import", f"Import of '{alias.name}' is not allowed")
            for alias in node.names
            if alias.name not in ALLOWED_IMPORTS
        ]
    if node.level:
        return [Finding(node.lineno, "check.import", "Relative imports are not allowed")]
    module = node.module or ""
    if module not in ALLOWED_IMPORTS:
        return [Finding(node.lineno, "check.import", f"Import from '{module}' is not allowed")]
    # `from torch import load` reaches a denylisted entry point without an attribute access.
    findings: list[Finding] = []
    for alias in node.names:
        dotted = f"{module}.{alias.name}"
        if _is_denylisted(dotted):
            findings.append(
                Finding(node.lineno, "check.torch_denylist", f"'{dotted}' is not allowed")
            )
    return findings


def _check_call(node: ast.Call) -> list[Finding]:
    if isinstance(node.func, ast.Name) and node.func.id in REFLECTION_BUILTINS:
        return [Finding(node.lineno, "check.reflection", f"'{node.func.id}' is not allowed")]
    return []


def _check_name(node: ast.Name) -> list[Finding]:
    if not isinstance(node.ctx, ast.Load):
        return []
    if node.id in _BUILTIN_NAMES and node.id not in SAFE_BUILTINS:
        return [Finding(node.lineno, "check.builtin", f"Builtin '{node.id}' is not allowed")]
    return []


def _check_attribute(node: ast.Attribute, aliases: dict[str, str]) -> list[Finding]:
    if node.attr.startswith("_") and not _is_super_init(node):
        return [
            Finding(node.lineno, "check.underscore", f"Attribute '{node.attr}' starts with '_'")
        ]
    dotted = _resolve(node, aliases)
    if dotted is not None and _is_denylisted(dotted):
        return [Finding(node.lineno, "check.torch_denylist", f"'{dotted}' is not allowed")]
    return []


def _is_super_init(node: ast.Attribute) -> bool:
    """Allow the one unavoidable dunder: ``super().__init__(...)`` in an nn.Module constructor."""
    return (
        node.attr == "__init__"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "super"
    )


def _is_denylisted(dotted: str) -> bool:
    return any(dotted == entry or dotted.startswith(entry + ".") for entry in TORCH_DENYLIST)


def _torch_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names bound by an allowed import to their dotted module path, for torch roots."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ALLOWED_IMPORTS:
                    aliases[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module in ALLOWED_IMPORTS:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _resolve(node: ast.Attribute, aliases: dict[str, str]) -> str | None:
    """Return the dotted path of an attribute chain rooted at an imported name, else None."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    root = aliases.get(current.id)
    if root is None:
        return None
    return ".".join([root, *reversed(parts)])
