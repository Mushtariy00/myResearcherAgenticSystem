"""Tests for the generated-code allowlist checker and its sandbox twin."""

import ast
from pathlib import Path

import pytest

import agentic_core.codecheck as codecheck
from agentic_core.codecheck import BLOCKS, MAX_SOURCE_BYTES, Finding, check_module

REPO = Path(codecheck.__file__).parents[4]

GOOD_MODEL = """\
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class Model(nn.Module):
    def __init__(self, base_channels: int = 8) -> None:
        super().__init__()
        self.encoder = nn.Conv2d(3, base_channels, kernel_size=3, padding=1)
        self.decoder = nn.Conv2d(base_channels, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = F.relu(self.encoder(x))
        return self.decoder(hidden)
"""

GOOD_LOSS = """\
from __future__ import annotations

import torch
from torch import nn

MIN_DEPTH = 1e-3


class Loss(nn.Module):
    def forward(self, prediction, target, valid_mask):
        mask = valid_mask & (target > MIN_DEPTH)
        diff = prediction[mask] - target[mask]
        return diff.abs().mean()
"""


BLOCKS_MODEL = """\
import torch
from torch import nn

from harness.blocks import DepthHead, Encoder, group_norm


class Model(nn.Module):
    def __init__(self, max_depth: float = 10.0) -> None:
        super().__init__()
        self.encoder = Encoder(channels=(8, 16))
        self.norm = group_norm(16)
        self.head = DepthHead(16, max_depth)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.norm(self.encoder(x)[-1]), x.shape[-2:])
"""


@pytest.mark.parametrize("source", [GOOD_MODEL, GOOD_LOSS, BLOCKS_MODEL])
def test_contract_abiding_modules_pass(source: str) -> None:
    assert check_module(source, filename="model.py") == []


@pytest.mark.parametrize(
    ("source", "message"),
    [
        # The module itself would reach its own imports (torch) as attributes, past the denylist.
        ("import harness.blocks\n", "import the blocks by name, from harness.blocks import"),
        ("from harness import blocks\n", "import the blocks by name, from harness.blocks import"),
        ("import harness\n", "import the blocks by name"),
        ("from harness.blocks import torch\n", "'torch' is not one of the harness's blocks"),
        ("from harness.blocks import *\n", "'*' is not one of the harness's blocks"),
        ("from harness.train import main\n", "Import from 'harness.train' is not allowed"),
    ],
)
def test_the_blocks_are_imported_by_name_and_nothing_else(source: str, message: str) -> None:
    findings = check_module(source, filename="model.py")
    assert [finding.code for finding in findings] == ["check.import"]
    assert message in findings[0].message


def test_the_allowed_blocks_are_the_harness_blocks_all() -> None:
    # The checker can't import the harness (no torch here): it reads blocks.py's __all__.
    tree = ast.parse((REPO / "sandbox" / "pytorch" / "harness" / "blocks.py").read_text())
    exported = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    )
    assert set(ast.literal_eval(exported)) == BLOCKS


REFUSALS = {
    "import os": ("import os\n", "check.import"),
    "from-import": ("from pathlib import Path\n", "check.import"),
    "open call": ("def f():\n    return open('x')\n", "check.builtin"),
    "exec name": ("def f():\n    exec('danger')\n", "check.builtin"),
    "underscore attr": ("def f(x):\n    return x.__class__\n", "check.underscore"),
    "getattr call": ("def f(x):\n    return getattr(x, 'y')\n", "check.reflection"),
    "torch.load": (
        "import torch\n\n\ndef f():\n    return torch.load('x')\n",
        "check.torch_denylist",
    ),
    "torch.from_file": (
        "import torch\n\n\ndef f():\n    return torch.from_file('x')\n",
        "check.torch_denylist",
    ),
    "storage from_file": (
        "import torch\n\n\ndef f():\n    return torch.UntypedStorage.from_file('x')\n",
        "check.torch_denylist",
    ),
    "torch.multiprocessing": (
        "from torch import multiprocessing\n",
        "check.torch_denylist",
    ),
    "top-level call": ("import math\n\nprint(math.pi)\n", "check.top_level"),
}


@pytest.mark.parametrize(("source", "code"), list(REFUSALS.values()), ids=list(REFUSALS))
def test_each_rule_refuses_an_ordinary_example(source: str, code: str) -> None:
    findings = check_module(source, filename="model.py")
    assert any(finding.code == code for finding in findings), findings


def test_oversized_files_are_refused() -> None:
    source = "x = 0\n" * 4000
    assert len(source.encode("utf-8")) > MAX_SOURCE_BYTES
    findings = check_module(source, filename="model.py")
    assert findings == [Finding(1, "check.too_large", findings[0].message)]
    assert str(MAX_SOURCE_BYTES) in findings[0].message


def test_findings_carry_the_right_line_numbers() -> None:
    source = "import os\nfrom torch import nn\n\n\ndef forward(x):\n    return x.__secret__\n"
    findings = check_module(source, filename="model.py")
    assert [(finding.line, finding.code) for finding in findings] == [
        (1, "check.import"),
        (6, "check.underscore"),
    ]


def test_sandbox_twin_is_byte_identical() -> None:
    core_copy = Path(codecheck.__file__)
    sandbox_copy = REPO / "sandbox" / "pytorch" / "harness" / "codecheck.py"
    assert sandbox_copy.read_bytes() == core_copy.read_bytes(), (
        "packages/core and sandbox/pytorch copies of codecheck.py have diverged; edit both"
    )
