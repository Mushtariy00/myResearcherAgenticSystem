"""Demo coding stage: PyTorch model and loss modules, a config, unit tests and a README.

The files are rendered from a few parameters. Every later attempt applies one more seeded
revision (an activation, a normalization layer, a learning rate...), so the diff between two
attempts changes a handful of real lines, and the README records each change and the feedback.
"""

import itertools
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from string import Template

from agentic_core.demo._profiles import DatasetSpec, Profile, dataset_spec, profile_for
from agentic_core.demo._text import code_text, feedback_line, markdown_text, revision_note, rng_for
from agentic_core.schemas import CodeFile, CodingOutput, MethodOutput, SmokeTest

GPU_NAME = "NVIDIA GeForce GTX 1060 6GB"

_ACTIVATIONS = {
    "relu": ("ReLU", "nn.ReLU(inplace=True)"),
    "silu": ("SiLU", "nn.SiLU(inplace=True)"),
    "gelu": ("GELU", "nn.GELU()"),
}
_AUX = {  # profile -> (config key, README description of the auxiliary weight)
    "depth": ("gradient_weight", "gradient-matching weight"),
    "segmentation": ("dice_weight", "Dice weight"),
    "classification": ("smoothing", "label smoothing"),
}


@dataclass(frozen=True)
class _Params:
    levels: int
    base_channels: int
    activation: str
    norm: str  # "batch" | "group"
    attention: bool
    dropout: float
    aux_weight: float  # depth: gradient term; segmentation: Dice term; classification: smoothing
    variance_focus: float  # SILog lambda (depth only)
    epochs: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    warmup_epochs: int
    scheduler: str
    seed: int


def coding(
    topic: str, method: MethodOutput, seed: int, attempt: int = 1, feedback: str = ""
) -> CodingOutput:
    """Model and loss modules for the recommended proposal of ``method``.

    ``seed`` should stay the same across attempts of one run: attempt ``n`` applies ``n - 1``
    revisions on top of the same base, which keeps the diff between attempts readable.
    """
    dataset_id = method.datasets[0]
    profile = profile_for(topic, dataset_id)
    dataset = dataset_spec(profile, dataset_id)
    base = _base_params(rng_for(seed, "coding", "base"), profile, dataset)
    params, changes = _revise(rng_for(seed, "coding", "revisions"), base, profile, attempt)
    proposal = code_text(method.recommended_option)
    metrics = _metric_names(profile, method.evaluation_metrics)
    files = [
        CodeFile(
            path="model.py",
            language="python",
            role="model",
            content=_model_py(profile, params, dataset, proposal, changes),
        ),
        CodeFile(
            path="losses.py",
            language="python",
            role="loss",
            content=_losses_py(profile, params),
        ),
        CodeFile(
            path="configs/train.yaml",
            language="yaml",
            role="config",
            content=_config_yaml(profile, params, dataset, proposal, metrics, attempt),
        ),
        CodeFile(
            path="tests/test_model.py",
            language="python",
            role="test",
            content=_tests_py(profile, dataset),
        ),
        CodeFile(
            path="README.md",
            language="markdown",
            role="docs",
            content=_readme(profile, params, dataset, method, changes, attempt, feedback),
        ),
    ]
    smoke_rng = rng_for(seed, "coding", "smoke", attempt)
    unit_seconds = round(smoke_rng.uniform(4.2, 9.8), 2)
    duration = round(unit_seconds + smoke_rng.uniform(18.0, 46.0), 1)
    size = _param_count(profile, params, dataset)
    summary = (
        f"{method.recommended_option}: {profile.model_class}, a {params.levels}-stage "
        f"{profile.architecture} with about {size / 1e6:.1f}M parameters, trained with "
        f"{profile.loss_label}. The smoke test passed: 4 unit tests and a 2-batch dry run on the "
        f"{GPU_NAME} in {duration:.0f} s."
    )
    if attempt > 1:
        summary += f" Attempt {attempt}: {changes[-1]}" if changes else f" Attempt {attempt}."
    note = revision_note(feedback)
    return CodingOutput(
        summary=f"{summary} {note}" if note else summary,
        files=files,
        entrypoint=f"model.py:{profile.model_class}",
        smoke_test=SmokeTest(
            passed=True,
            duration_seconds=duration,
            log=_smoke_log(smoke_rng, profile, metrics, unit_seconds),
        ),
    )


def _base_params(rng: random.Random, profile: Profile, dataset: DatasetSpec) -> _Params:
    height, width = dataset.input_size
    pixels = height * width
    batch_size = 4 if pixels >= 400_000 else 8 if pixels >= 100_000 else 128
    aux = {
        "depth": (0.25, 0.5),
        "segmentation": (0.5, 1.0),
        "classification": (0.05, 0.1),
    }[profile.key]
    return _Params(
        levels=4,
        base_channels=rng.choice((32, 32, 48)),
        activation=rng.choice(("relu", "relu", "silu")),
        norm="batch",
        attention=rng.random() < 0.3,
        dropout=0.0,
        aux_weight=rng.choice(aux),
        variance_focus=rng.choice((0.85, 0.5)),
        epochs=rng.randint(12, 24),
        batch_size=batch_size,
        learning_rate=rng.choice((3e-4, 2e-4, 5e-4)),
        weight_decay=rng.choice((1e-4, 1e-2)),
        warmup_epochs=1,
        scheduler=rng.choice(("cosine", "cosine", "onecycle")),
        seed=rng.choice((0, 7, 42, 1234, 2024, 3407)),
    )


type _Revision = Callable[[_Params, Profile], tuple[_Params, str] | None]


def _gelu(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.activation == "gelu":
        return None
    old = _ACTIVATIONS[p.activation][0]
    return replace(p, activation="gelu"), f"Switched the activation from {old} to GELU."


def _attention(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.attention:
        return None
    return replace(p, attention=True), "Added a squeeze-and-excitation block to the bottleneck."


def _group_norm(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.norm == "group":
        return None
    return (
        replace(p, norm="group"),
        f"Replaced BatchNorm with GroupNorm, which stays stable at batch size {p.batch_size}.",
    )


def _lower_learning_rate(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.learning_rate <= 1e-4:
        return None
    new = p.learning_rate / 2
    return (
        replace(p, learning_rate=new, warmup_epochs=2),
        f"Halved the learning rate to {_decimal(new)} and warm up for 2 epochs.",
    )


def _dropout(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.dropout > 0:
        return None
    return replace(p, dropout=0.1), "Added dropout (p = 0.1) before the prediction head."


def _longer(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.epochs >= 30:
        return None
    epochs = min(30, p.epochs + 6)
    return replace(p, epochs=epochs), f"Extended training from {p.epochs} to {epochs} epochs."


def _aux_weight(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    limit = 0.2 if profile.key == "classification" else 2.0
    new = round(p.aux_weight * 2, 3)
    if new > limit:
        return None
    label = _AUX[profile.key][1]
    return replace(p, aux_weight=new), f"Raised the {label} from {p.aux_weight:g} to {new:g}."


def _wider(p: _Params, profile: Profile) -> tuple[_Params, str] | None:
    if p.base_channels >= 64:
        return None
    channels = p.base_channels + 16
    return (
        replace(p, base_channels=channels),
        f"Widened the network from {p.base_channels} to {channels} base channels.",
    )


_REVISIONS: tuple[_Revision, ...] = (
    _gelu,
    _attention,
    _group_norm,
    _lower_learning_rate,
    _dropout,
    _longer,
    _aux_weight,
    _wider,
)


def _revise(
    rng: random.Random, base: _Params, profile: Profile, attempt: int
) -> tuple[_Params, list[str]]:
    """Apply ``attempt - 1`` revisions in a seeded order; returns the params and the changes."""
    order = list(_REVISIONS)
    rng.shuffle(order)
    params, changes = base, []
    for revision in order:
        if len(changes) >= attempt - 1:
            break
        revised = revision(params, profile)
        if revised is not None:
            params = revised[0]
            changes.append(revised[1])
    return params, changes


def _metric_names(profile: Profile, requested: list[str]) -> list[str]:
    known = {metric.name for metric in profile.metrics}
    names = [name for name in requested if name in known][:3]
    for metric in profile.metrics:
        if len(names) >= 2:
            break
        if metric.name not in names:
            names.append(metric.name)
    return names


def _decimal(value: float) -> str:
    """0.0003 instead of 3e-04: YAML 1.1 loaders read the exponent form as a string."""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _float(value: float) -> str:
    """A float literal that stays a float in Python and YAML: 0.0, 0.1, 0.25."""
    return repr(float(value))


def _param_count(profile: Profile, p: _Params, dataset: DatasetSpec) -> int:
    def block(cin: int, cout: int) -> int:  # two 3x3 convs without bias, two norm layers
        return 9 * cin * cout + 9 * cout * cout + 4 * cout

    widths = [p.base_channels * 2**level for level in range(p.levels)]
    total = block(3, widths[0]) + sum(block(a, b) for a, b in itertools.pairwise(widths))
    if p.attention:
        channels = widths[-1]
        total += 2 * channels * (channels // 8) + channels // 8 + channels
    if profile.key == "classification":
        return total + widths[-1] * dataset.classes + dataset.classes
    total += sum(block(b + a, a) for a, b in itertools.pairwise(widths))
    outputs = 1 if profile.key == "depth" else dataset.classes
    return total + widths[0] * outputs + outputs


# --- model.py ---------------------------------------------------------------------------------

_HEADER = Template('''\
"""$model_class: $proposal.

$purpose
The experiment harness owns the data loader, the metrics and the training loop;
this module only defines the network.
"""

from __future__ import annotations

import torch
from torch import nn
$functional$revisions

def norm(channels: int) -> nn.Module:
    """$norm_doc"""
    return $norm_expr


class ConvBlock(nn.Module):
    """Two 3x3 convolutions, each followed by normalization and $act_name."""

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, stride=stride, padding=1, bias=False),
            norm(out_channels),
            $act,
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            norm(out_channels),
            $act,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body(x)
$attention
''')

_SQUEEZE_EXCITE = '''

class SqueezeExcite(nn.Module):
    """Channel attention for the bottleneck (Hu et al., 2018)."""

    def __init__(self, channels: int, reduction: int = 8) -> None:
        super().__init__()
        self.gate = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(channels, channels // reduction, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels // reduction, channels, kernel_size=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.gate(x)
'''

_UNET = Template('''

class $model_class(nn.Module):
    """$class_doc"""

    def __init__(
        self,
        $first_arg,
        base_channels: int = $base_channels,
        dropout: float = $dropout,
    ) -> None:
        super().__init__()
        widths = [base_channels * 2**level for level in range($levels)]
        self.stem = ConvBlock(3, widths[0])
        self.down = nn.ModuleList(
            ConvBlock(widths[level], widths[level + 1], stride=2) for level in range($down)
        )
        self.bottleneck = $bottleneck
        self.up = nn.ModuleList(
            ConvBlock(widths[level + 1] + widths[level], widths[level])
            for level in reversed(range($down))
        )
        self.head = nn.Sequential(
            nn.Dropout2d(dropout), nn.Conv2d(widths[0], $out_channels, kernel_size=1)
        )$init_tail

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        skips = []
        x = self.stem(image)
        for block in self.down:
            skips.append(x)
            x = block(x)
        x = self.bottleneck(x)
        for block, skip in zip(self.up, reversed(skips)):
            x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            x = block(torch.cat([x, skip], dim=1))
        return $output
''')

_CNN = Template('''

class $model_class(nn.Module):
    """A compact convolutional network with a global-pooling classifier head."""

    def __init__(
        self,
        num_classes: int = $classes,
        base_channels: int = $base_channels,
        dropout: float = $dropout,
    ) -> None:
        super().__init__()
        widths = [base_channels * 2**stage for stage in range($levels)]
        self.features = nn.Sequential(
            ConvBlock(3, widths[0]),
            *(ConvBlock(widths[stage], widths[stage + 1], stride=2) for stage in range($down)),
            $bottleneck,
        )
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(widths[-1], num_classes),
        )

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(image))
''')


def _model_py(
    profile: Profile, p: _Params, dataset: DatasetSpec, proposal: str, changes: list[str]
) -> str:
    act_name, act = _ACTIVATIONS[p.activation]
    if p.norm == "group":
        norm_doc = "GroupNorm: stable at the small batch sizes a 6 GB GPU allows."
        norm_expr = "nn.GroupNorm(num_groups=8, num_channels=channels)"
    else:
        norm_doc = f"Batch normalization (batch size {p.batch_size})."
        norm_expr = "nn.BatchNorm2d(channels)"
    revisions = "".join(
        f"\n# Attempt {index}: {code_text(change, 80)}" for index, change in enumerate(changes, 2)
    )
    purpose = f"Generated by the coding stage for {profile.task} on {dataset.label}."
    functional = "from torch.nn import functional as F\n"
    header = _HEADER.substitute(
        model_class=profile.model_class,
        proposal=proposal.rstrip("."),
        purpose=purpose,
        functional="" if profile.key == "classification" else functional,
        revisions=f"{revisions}\n" if revisions else "",
        norm_doc=norm_doc,
        norm_expr=norm_expr,
        act_name=act_name,
        act=act,
        attention=_SQUEEZE_EXCITE.rstrip("\n") if p.attention else "",
    )
    bottleneck = "SqueezeExcite(widths[-1])" if p.attention else "nn.Identity()"
    common = {
        "model_class": profile.model_class,
        "base_channels": p.base_channels,
        "dropout": _float(p.dropout),
        "levels": p.levels,
        "down": p.levels - 1,
        "bottleneck": bottleneck,
    }
    if profile.key == "classification":
        body = _CNN.substitute(common, classes=dataset.classes)
    elif profile.key == "depth":
        body = _UNET.substitute(
            common,
            class_doc="U-Net-style encoder-decoder that predicts metric depth in metres.",
            first_arg="max_depth: float = 10.0",
            out_channels="1",
            init_tail="\n        self.max_depth = max_depth",
            output="self.max_depth * torch.sigmoid(self.head(x))",
        )
    else:
        body = _UNET.substitute(
            common,
            class_doc="U-Net-style encoder-decoder that predicts per-pixel class logits.",
            first_arg=f"num_classes: int = {dataset.classes}",
            out_channels="num_classes",
            init_tail="",
            output="self.head(x)",
        )
    return header.rstrip("\n") + "\n" + body


# --- losses.py --------------------------------------------------------------------------------

_DEPTH_LOSS = Template('''\
"""Training objective for $model_class: SILog loss plus a gradient-matching term."""

from __future__ import annotations

import torch
from torch import nn

MIN_DEPTH = 1e-3  # zero depth marks missing sensor readings, as in the harness metrics


class SILogLoss(nn.Module):
    """Scale-invariant log loss (Eigen et al., 2014) on valid pixels only."""

    def __init__(self, variance_focus: float = $variance_focus, scale: float = 10.0) -> None:
        super().__init__()
        self.variance_focus = variance_focus
        self.scale = scale

    def forward(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        mask = target > MIN_DEPTH
        g = torch.log(prediction[mask].clamp_min(MIN_DEPTH)) - torch.log(target[mask])
        variance = (g**2).mean() - self.variance_focus * g.mean() ** 2
        return self.scale * torch.sqrt(variance.clamp_min(1e-8))


def _gradients(depth: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    return depth[..., :, 1:] - depth[..., :, :-1], depth[..., 1:, :] - depth[..., :-1, :]


class GradientMatchingLoss(nn.Module):
    """L1 distance between predicted and true depth gradients, for sharper object edges."""

    def forward(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        valid = (target > MIN_DEPTH).float()
        pred_dx, pred_dy = _gradients(prediction)
        true_dx, true_dy = _gradients(target)
        mask_dx = valid[..., :, 1:] * valid[..., :, :-1]
        mask_dy = valid[..., 1:, :] * valid[..., :-1, :]
        loss_dx = ((pred_dx - true_dx).abs() * mask_dx).sum() / mask_dx.sum().clamp_min(1.0)
        loss_dy = ((pred_dy - true_dy).abs() * mask_dy).sum() / mask_dy.sum().clamp_min(1.0)
        return loss_dx + loss_dy


class $loss_class(nn.Module):
    """The objective the harness calls: SILog plus a weighted gradient-matching term."""

    def __init__(self, gradient_weight: float = $aux_weight) -> None:
        super().__init__()
        self.silog = SILogLoss()
        self.gradient = GradientMatchingLoss()
        self.gradient_weight = gradient_weight

    def forward(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        loss = self.silog(prediction, target)
        if self.gradient_weight > 0:
            loss = loss + self.gradient_weight * self.gradient(prediction, target)
        return loss
''')

_SEGMENTATION_LOSS = Template('''\
"""Training objective for $model_class: $loss_label."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

IGNORE_INDEX = 255  # unlabeled pixels, as in the harness metrics


class DiceLoss(nn.Module):
    """Soft Dice loss averaged over classes; rare classes weigh as much as frequent ones."""

    def __init__(self, smooth: float = 1.0) -> None:
        super().__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        classes = logits.shape[1]
        valid = (target != IGNORE_INDEX).unsqueeze(1).float()
        probs = logits.softmax(dim=1) * valid
        labels = F.one_hot(target.clamp(0, classes - 1), classes).permute(0, 3, 1, 2).float()
        labels = labels * valid
        overlap = (probs * labels).sum(dim=(0, 2, 3))
        total = probs.sum(dim=(0, 2, 3)) + labels.sum(dim=(0, 2, 3))
        return 1 - ((2 * overlap + self.smooth) / (total + self.smooth)).mean()


class $loss_class(nn.Module):
    """Cross-entropy plus a weighted Dice term."""

    def __init__(self, dice_weight: float = $aux_weight) -> None:
        super().__init__()
        self.cross_entropy = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
        self.dice = DiceLoss()
        self.dice_weight = dice_weight

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return self.cross_entropy(logits, target) + self.dice_weight * self.dice(logits, target)
''')

_CLASSIFICATION_LOSS = Template('''\
"""Training objective for $model_class: $loss_label."""

from __future__ import annotations

import torch
from torch import nn


class $loss_class(nn.Module):
    """Cross-entropy against targets smoothed toward the uniform distribution."""

    def __init__(self, smoothing: float = $aux_weight) -> None:
        super().__init__()
        self.smoothing = smoothing

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        log_probs = logits.log_softmax(dim=-1)
        nll = -log_probs.gather(1, target.unsqueeze(1)).squeeze(1)
        uniform = -log_probs.mean(dim=-1)
        return ((1 - self.smoothing) * nll + self.smoothing * uniform).mean()
''')


def _losses_py(profile: Profile, p: _Params) -> str:
    template = {
        "depth": _DEPTH_LOSS,
        "segmentation": _SEGMENTATION_LOSS,
        "classification": _CLASSIFICATION_LOSS,
    }[profile.key]
    return template.substitute(
        model_class=profile.model_class,
        loss_class=profile.loss_class,
        loss_label=profile.loss_label,
        variance_focus=_float(p.variance_focus),
        aux_weight=_float(p.aux_weight),
    )


# --- tests/test_model.py ----------------------------------------------------------------------

_DEPTH_TESTS = Template('''\
"""Unit tests the smoke test runs before any GPU time is spent."""

import torch

from losses import $loss_class
from model import $model_class


def test_output_matches_the_input_resolution() -> None:
    model = $model_class().eval()
    with torch.no_grad():
        depth = model(torch.randn(2, 3, 96, 128))
    assert depth.shape == (2, 1, 96, 128)


def test_depth_is_positive_and_bounded() -> None:
    model = $model_class(max_depth=10.0).eval()
    with torch.no_grad():
        depth = model(torch.randn(1, 3, 64, 64))
    assert torch.all(depth > 0) and torch.all(depth < 10.0)


def test_loss_ignores_missing_depth() -> None:
    target = torch.rand(1, 1, 32, 32) * 5 + 0.5
    prediction = target.clone()
    target[..., :8, :] = 0.0  # missing sensor readings
    prediction[..., :8, :] = 3.0
    assert $loss_class()(prediction, target).item() < 1e-2


def test_one_optimizer_step_lowers_the_loss() -> None:
    torch.manual_seed(0)
    model, criterion = $model_class(), $loss_class()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    images, target = torch.randn(2, 3, 64, 64), torch.rand(2, 1, 64, 64) * 9 + 0.5
    before = criterion(model(images), target)
    before.backward()
    optimizer.step()
    assert criterion(model(images), target).item() < before.item()
''')

_SEGMENTATION_TESTS = Template('''\
"""Unit tests the smoke test runs before any GPU time is spent."""

import torch

from losses import $loss_class
from model import $model_class


def test_logits_match_the_input_resolution() -> None:
    model = $model_class(num_classes=$classes).eval()
    with torch.no_grad():
        logits = model(torch.randn(2, 3, 96, 128))
    assert logits.shape == (2, $classes, 96, 128)


def test_loss_ignores_unlabeled_pixels() -> None:
    logits = torch.randn(1, $classes, 16, 16)
    target = torch.full((1, 16, 16), 255)
    target[..., :8] = 1
    loss = $loss_class()(logits, target)
    assert torch.isfinite(loss)


def test_perfect_logits_give_a_small_loss() -> None:
    target = torch.randint(0, $classes, (1, 16, 16))
    logits = torch.nn.functional.one_hot(target, $classes).permute(0, 3, 1, 2).float() * 50
    assert $loss_class()(logits, target).item() < 0.05


def test_one_optimizer_step_lowers_the_loss() -> None:
    torch.manual_seed(0)
    model, criterion = $model_class(num_classes=$classes), $loss_class()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    images, target = torch.randn(2, 3, 64, 64), torch.randint(0, $classes, (2, 64, 64))
    before = criterion(model(images), target)
    before.backward()
    optimizer.step()
    assert criterion(model(images), target).item() < before.item()
''')

_CLASSIFICATION_TESTS = Template('''\
"""Unit tests the smoke test runs before any GPU time is spent."""

import torch

from losses import $loss_class
from model import $model_class


def test_one_logit_per_class() -> None:
    model = $model_class(num_classes=$classes).eval()
    with torch.no_grad():
        logits = model(torch.randn(4, 3, $height, $width))
    assert logits.shape == (4, $classes)


def test_smoothing_zero_is_plain_cross_entropy() -> None:
    logits, target = torch.randn(8, $classes), torch.randint(0, $classes, (8,))
    expected = torch.nn.functional.cross_entropy(logits, target)
    assert torch.allclose($loss_class(smoothing=0.0)(logits, target), expected)


def test_smoothing_penalizes_overconfidence() -> None:
    target = torch.zeros(1, dtype=torch.long)
    confident = torch.full((1, $classes), -20.0)
    confident[0, 0] = 20.0
    assert $loss_class(smoothing=0.1)(confident, target) > $loss_class(smoothing=0.0)(
        confident, target
    )


def test_one_optimizer_step_lowers_the_loss() -> None:
    torch.manual_seed(0)
    model, criterion = $model_class(num_classes=$classes), $loss_class()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    images, target = torch.randn(8, 3, $height, $width), torch.randint(0, $classes, (8,))
    before = criterion(model(images), target)
    before.backward()
    optimizer.step()
    assert criterion(model(images), target).item() < before.item()
''')


def _tests_py(profile: Profile, dataset: DatasetSpec) -> str:
    template = {
        "depth": _DEPTH_TESTS,
        "segmentation": _SEGMENTATION_TESTS,
        "classification": _CLASSIFICATION_TESTS,
    }[profile.key]
    height, width = dataset.input_size
    return template.substitute(
        model_class=profile.model_class,
        loss_class=profile.loss_class,
        classes=min(dataset.classes, 1000),
        height=min(height, 64),
        width=min(width, 64),
    )


# --- configs/train.yaml -----------------------------------------------------------------------

_CONFIG = Template("""\
# Experiment config for "$proposal" (attempt $attempt).
# The harness validates every value against its bounds before the job starts.
task: $task
seed: $seed
require_gpu: true
model:
  module: model.py
  class: $model_class
  kwargs:
$model_kwargs
loss:
  module: losses.py
  class: $loss_class
  kwargs:
    $aux_key: $aux_weight
data:
  dataset: $dataset
  input_size: [$height, $width]
  batch_size: $batch_size
  num_workers: 2
training:
  epochs: $epochs
  optimizer: adamw
  learning_rate: $learning_rate
  weight_decay: $weight_decay
  scheduler: $scheduler
  warmup_epochs: $warmup_epochs
  amp: true
  clip_grad_norm: 1.0
evaluation:
  metrics: [$metrics]
""")


def _config_yaml(
    profile: Profile,
    p: _Params,
    dataset: DatasetSpec,
    proposal: str,
    metrics: list[str],
    attempt: int,
) -> str:
    first = "max_depth: 10.0" if profile.key == "depth" else f"num_classes: {dataset.classes}"
    kwargs = [first, f"base_channels: {p.base_channels}", f"dropout: {_float(p.dropout)}"]
    height, width = dataset.input_size
    return _CONFIG.substitute(
        proposal=proposal.replace('"', "'"),
        attempt=attempt,
        task=f"{dataset.id}_{profile.key}",
        seed=p.seed,
        model_class=profile.model_class,
        model_kwargs="\n".join(f"    {line}" for line in kwargs),
        loss_class=profile.loss_class,
        aux_key=_AUX[profile.key][0],
        aux_weight=_float(p.aux_weight),
        dataset=dataset.id,
        height=height,
        width=width,
        batch_size=p.batch_size,
        epochs=p.epochs,
        learning_rate=_decimal(p.learning_rate),
        weight_decay=_decimal(p.weight_decay),
        scheduler=p.scheduler,
        warmup_epochs=p.warmup_epochs,
        metrics=", ".join(metrics),
    )


# --- README.md --------------------------------------------------------------------------------


def _readme(
    profile: Profile,
    p: _Params,
    dataset: DatasetSpec,
    method: MethodOutput,
    changes: list[str],
    attempt: int,
    feedback: str,
) -> str:
    proposal = markdown_text(method.recommended_option)
    size = _param_count(profile, p, dataset) / 1e6
    act_name = _ACTIVATIONS[p.activation][0]
    norm = "GroupNorm" if p.norm == "group" else "BatchNorm"
    aux_key, aux_label = _AUX[profile.key]
    schedule = "cosine decay" if p.scheduler == "cosine" else "one-cycle schedule"
    attention = "a squeeze-and-excitation gate in the bottleneck" if p.attention else "no attention"
    metrics = ", ".join(f"`{name}`" for name in _metric_names(profile, method.evaluation_metrics))
    lines = [
        f"# {profile.model_class}: {proposal}",
        "",
        f"Implements the method stage's recommendation, **{proposal}**, for {profile.task} on "
        f"{dataset.label}. The sandbox harness owns the data loader, the metrics and the "
        "training loop; this package only adds the model and the loss.",
        "",
        "## Files",
        "",
        "| File | Contents |",
        "| --- | --- |",
        f"| `model.py` | `{profile.model_class}`: {p.levels}-stage {profile.architecture}, about "
        f"{size:.1f}M parameters |",
        f"| `losses.py` | `{profile.loss_class}`: {profile.loss_label} ({aux_label} "
        f"{p.aux_weight:g}) |",
        f"| `configs/train.yaml` | {p.epochs} epochs, AdamW, learning rate "
        f"{_decimal(p.learning_rate)}, batch size {p.batch_size}, {schedule}, mixed precision |",
        "| `tests/test_model.py` | Output shape, value range, masking and a one-step training "
        "check |",
        "",
        "## Run",
        "",
        "```bash",
        "python -m pytest -q tests/test_model.py",
        "python -m harness.train --config configs/train.yaml --dry-run",
        "python -m harness.train --config configs/train.yaml",
        "```",
        "",
        "## Design notes",
        "",
        f"- {act_name} activations and {norm} in every block; {attention}.",
        f"- The {aux_label} (`{aux_key}`) is set in `configs/train.yaml`, so it can be tuned "
        "without touching the code.",
        f"- Batch size {p.batch_size} with mixed precision fits the {GPU_NAME}; gradients are "
        "clipped at norm 1.0.",
        f"- Evaluated with {metrics}, computed by the harness.",
    ]
    if changes or attempt > 1:
        lines += ["", "## Revision history", ""]
        lines += [f"- Attempt {index}: {change}" for index, change in enumerate(changes, 2)]
        if not changes:
            lines.append(f"- Attempt {attempt}: re-generated without code changes.")
        text = feedback_line(feedback)
        if text:
            lines += ["", f"Reviewer feedback for attempt {attempt}: {markdown_text(text)}"]
    return "\n".join(lines) + "\n"


def _smoke_log(rng: random.Random, profile: Profile, metrics: list[str], seconds: float) -> str:
    loss = rng.uniform(1.6, 2.6)
    first = profile.metrics[0]
    metric = metrics[0] if metrics else first.name
    train_value = rng.uniform(*first.start)
    val_value = train_value * rng.uniform(1.01, 1.08)
    memory = rng.uniform(1.4, 3.6)
    return "\n".join(
        [
            "$ python -m pytest -q tests/test_model.py",
            "...." + " " * 69 + "[100%]",
            f"4 passed in {seconds:.2f}s",
            "$ python -m harness.train --config configs/train.yaml --dry-run",
            f"INFO epoch 0 step 0 loss {loss:.4f}",
            f"INFO epoch 0 train {{'loss': {loss * 0.97:.4f}, '{metric}': {train_value:.4f}}} "
            f"val {{'loss': {loss * 1.02:.4f}, '{metric}': {val_value:.4f}}}",
            f"INFO dry run finished: 2 train and 2 val batches on {GPU_NAME}",
            f"INFO peak GPU memory {memory:.2f} GB of 6.00 GB",
        ]
    )
