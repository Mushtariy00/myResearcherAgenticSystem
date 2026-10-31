"""Tested building blocks for the coding agent's model.py and loss.py.

Generated code imports them by name (`from harness.blocks import Encoder, UpBlock`); the
checker allows the names in __all__ and nothing else from this module, never the module itself,
whose own imports would then be reachable as attributes. They cover what generated code got wrong
most in the Phase 3 exit run (2026-10-31): GroupNorm group counts that don't divide the channels,
attention over feature maps with mismatched shapes, skip connections at odd sizes, and masked
depth losses. Feature maps are (B, C, H, W) throughout; each docstring gives the shapes.
"""

from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn
from torch.nn import functional as F

__all__ = [
    "ConvNormAct",
    "CrossAttention",
    "DepthHead",
    "Encoder",
    "FeatureAttention",
    "GuidedUpsample",
    "InvertedResidual",
    "SqueezeExcite",
    "UpBlock",
    "gradient_loss",
    "group_norm",
    "masked_l1",
    "resize_to",
    "silog_loss",
    "ssim_loss",
]

_ACTIVATIONS: dict[str, type[nn.Module]] = {
    "relu": nn.ReLU,
    "relu6": nn.ReLU6,
    "gelu": nn.GELU,
    "silu": nn.SiLU,
    "none": nn.Identity,
}


def group_norm(channels: int, groups: int = 8) -> nn.GroupNorm:
    """GroupNorm over ``channels`` with the most groups, up to ``groups``, that divide them (1 at
    worst): group_norm(144) has 8 groups, group_norm(36) 6, group_norm(7) 7."""
    groups = max(1, min(int(groups), int(channels)))
    while channels % groups:
        groups -= 1
    return nn.GroupNorm(groups, channels)


def resize_to(x: torch.Tensor, size: Sequence[int]) -> torch.Tensor:
    """Bilinear resize of (B, C, h, w) to size = (H, W), e.g. resize_to(x, image.shape[-2:])."""
    target = (int(size[0]), int(size[1]))
    if tuple(x.shape[-2:]) == target:
        return x
    return F.interpolate(x, size=target, mode="bilinear", align_corners=False)


def _heads(channels: int, heads: int) -> int:
    """The most attention heads, up to ``heads``, that divide ``channels``."""
    heads = max(1, min(int(heads), int(channels)))
    while channels % heads:
        heads -= 1
    return heads


class ConvNormAct(nn.Module):
    """Conv2d, GroupNorm, activation ("relu", "relu6", "gelu", "silu" or "none"). The padding
    keeps the size at stride 1: (B, in_channels, H, W) -> (B, out_channels, ceil(H / stride),
    ceil(W / stride)). groups=in_channels makes it depthwise."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        stride: int = 1,
        groups: int = 1,
        act: str = "relu",
    ) -> None:
        super().__init__()
        if act not in _ACTIVATIONS:
            raise ValueError(f"act must be one of {', '.join(_ACTIVATIONS)}, not {act!r}")
        self.conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size,
            stride=stride,
            padding=kernel_size // 2,
            groups=groups,
            bias=False,
        )
        self.norm = group_norm(out_channels)
        self.act = _ACTIVATIONS[act]()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.norm(self.conv(x)))


class InvertedResidual(nn.Module):
    """MobileNetV2's block: a 1x1 expansion, a 3x3 depthwise convolution at ``stride``, a 1x1
    projection, and a residual when the shape is kept. (B, in_channels, H, W) ->
    (B, out_channels, ceil(H / stride), ceil(W / stride))."""

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1, expand: int = 4) -> None:
        super().__init__()
        hidden = in_channels * max(1, int(expand))
        layers: list[nn.Module] = []
        if hidden != in_channels:
            layers.append(ConvNormAct(in_channels, hidden, 1, act="relu6"))
        layers += [
            ConvNormAct(hidden, hidden, 3, stride=stride, groups=hidden, act="relu6"),
            nn.Conv2d(hidden, out_channels, 1, bias=False),
            group_norm(out_channels),
        ]
        self.body = nn.Sequential(*layers)
        self.residual = stride == 1 and in_channels == out_channels

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.body(x)
        return x + out if self.residual else out


class Encoder(nn.Module):
    """A MobileNetV2-style encoder, from scratch: a stride-2 stem, then one stage per entry of
    ``channels`` (``depths`` blocks each), every stage after the first halving the size.
    forward(x) returns one feature map per stage, finest first: stage i has channels[i] channels
    at stride 2 ** (i + 1), so x (B, 3, H, W) -> [(B, channels[0], H/2, W/2),
    (B, channels[1], H/4, W/4), ...], sizes rounded up. ``encoder.channels`` and
    ``encoder.strides`` give them for the decoder."""

    def __init__(
        self,
        channels: Sequence[int] = (16, 24, 32, 64, 96),
        depths: Sequence[int] = (1, 2, 2, 2, 1),
        expand: int = 4,
        in_channels: int = 3,
    ) -> None:
        super().__init__()
        if not channels or len(channels) != len(depths):
            raise ValueError("Encoder needs one depth per stage: len(depths) == len(channels)")
        self.channels = tuple(int(width) for width in channels)
        self.strides = tuple(2 ** (index + 1) for index in range(len(self.channels)))
        self.stem = ConvNormAct(in_channels, self.channels[0], 3, stride=2, act="relu6")
        stages: list[nn.Module] = []
        previous = self.channels[0]
        for index, (width, depth) in enumerate(zip(self.channels, depths, strict=True)):
            blocks: list[nn.Module] = []
            for number in range(max(1, int(depth))):
                stride = 2 if index > 0 and number == 0 else 1
                blocks.append(InvertedResidual(previous, width, stride=stride, expand=expand))
                previous = width
            stages.append(nn.Sequential(*blocks))
        self.stages = nn.ModuleList(stages)

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        features: list[torch.Tensor] = []
        x = self.stem(x)
        for stage in self.stages:
            x = stage(x)
            features.append(x)
        return features


class FeatureAttention(nn.Module):
    """Multi-head self-attention between a feature map's positions, then a 1x1 MLP, each with a
    residual: (B, C, H, W) -> (B, C, H, W). Keys and values are average-pooled by ``kv_stride``
    to bound memory; ``heads`` is lowered until it divides the channels. Use it on coarse stages
    (stride 16 or 32): attention over a full 480 x 640 frame does not fit a 6 GB GPU."""

    def __init__(self, channels: int, heads: int = 4, kv_stride: int = 1, mlp_ratio: int = 2) -> None:
        super().__init__()
        self.heads = _heads(channels, heads)
        self.kv_stride = max(1, int(kv_stride))
        self.norm = group_norm(channels, 1)
        self.q = nn.Conv2d(channels, channels, 1, bias=False)
        self.kv = nn.Conv2d(channels, channels * 2, 1, bias=False)
        self.proj = nn.Conv2d(channels, channels, 1)
        hidden = channels * max(1, int(mlp_ratio))
        self.mlp = nn.Sequential(
            group_norm(channels, 1),
            nn.Conv2d(channels, hidden, 1),
            nn.GELU(),
            nn.Conv2d(hidden, channels, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        y = self.norm(x)
        context = F.avg_pool2d(y, self.kv_stride, ceil_mode=True) if self.kv_stride > 1 else y
        q = self.q(y).reshape(b, self.heads, c // self.heads, h * w).transpose(2, 3)
        k, v = self.kv(context).flatten(2).chunk(2, dim=1)  # (B, C, N) each
        k = k.reshape(b, self.heads, c // self.heads, -1).transpose(2, 3)
        v = v.reshape(b, self.heads, c // self.heads, -1).transpose(2, 3)
        out = F.scaled_dot_product_attention(q, k, v)  # (B, heads, H*W, C/heads)
        x = x + self.proj(out.transpose(2, 3).reshape(b, c, h, w))
        return x + self.mlp(x)


class CrossAttention(nn.Module):
    """A feature map's positions attend to a context, with a residual: x (B, C, H, W) and
    context (B, context_channels, h, w), a feature map of any size (a coarser stage), or
    (B, N, context_channels), tokens such as learned ones (a batch of 1 is shared by the whole
    batch) -> (B, C, H, W). ``heads`` is lowered until it divides the channels."""

    def __init__(self, channels: int, context_channels: int, heads: int = 4) -> None:
        super().__init__()
        self.heads = _heads(channels, heads)
        self.norm = group_norm(channels, 1)
        self.q = nn.Conv2d(channels, channels, 1, bias=False)
        self.kv = nn.Linear(context_channels, channels * 2, bias=False)
        self.proj = nn.Conv2d(channels, channels, 1)

    def forward(self, x: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        b, c, h, w = x.shape
        if context.dim() == 4:
            context = context.flatten(2).transpose(1, 2)  # (B, h*w, context_channels)
        if context.shape[0] == 1 and b > 1:
            context = context.expand(b, -1, -1)
        q = self.q(self.norm(x)).reshape(b, self.heads, c // self.heads, h * w).transpose(2, 3)
        k, v = self.kv(context).chunk(2, dim=-1)  # (B, N, C) each
        k = k.reshape(b, -1, self.heads, c // self.heads).transpose(1, 2)
        v = v.reshape(b, -1, self.heads, c // self.heads).transpose(1, 2)
        out = F.scaled_dot_product_attention(q, k, v)  # (B, heads, H*W, C/heads)
        return x + self.proj(out.transpose(2, 3).reshape(b, c, h, w))


class SqueezeExcite(nn.Module):
    """Channel attention: a global average, a bottleneck and a sigmoid gate per channel.
    (B, C, H, W) -> (B, C, H, W)."""

    def __init__(self, channels: int, reduction: int = 4) -> None:
        super().__init__()
        hidden = max(4, channels // max(1, int(reduction)))
        self.gate = nn.Sequential(
            nn.Conv2d(channels, hidden, 1),
            nn.ReLU(inplace=True),
            nn.Conv2d(hidden, channels, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.gate(F.adaptive_avg_pool2d(x, 1))


class UpBlock(nn.Module):
    """A decoder step: x resized to the skip's exact size (so odd sizes never break the
    concatenation), the skip concatenated, two ConvNormAct. x (B, in_channels, h, w) and skip
    (B, skip_channels, H, W) -> (B, out_channels, H, W)."""

    def __init__(self, in_channels: int, skip_channels: int, out_channels: int) -> None:
        super().__init__()
        self.fuse = nn.Sequential(
            ConvNormAct(in_channels + skip_channels, out_channels),
            ConvNormAct(out_channels, out_channels),
        )

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        return self.fuse(torch.cat([resize_to(x, skip.shape[-2:]), skip], dim=1))


class GuidedUpsample(nn.Module):
    """Features upsampled to the guide's size and refined with it, as in guided decoding: the
    guide (the input image, or a fine feature map) goes through a small convolution first.
    x (B, in_channels, h, w) and guide (B, guide_channels, H, W) -> (B, out_channels, H, W)."""

    def __init__(self, in_channels: int, guide_channels: int, out_channels: int) -> None:
        super().__init__()
        guided = max(8, out_channels // 2)
        self.guide = ConvNormAct(guide_channels, guided)
        self.fuse = nn.Sequential(
            ConvNormAct(in_channels + guided, out_channels),
            ConvNormAct(out_channels, out_channels),
        )

    def forward(self, x: torch.Tensor, guide: torch.Tensor) -> torch.Tensor:
        up = resize_to(x, guide.shape[-2:])
        return self.fuse(torch.cat([up, self.guide(guide)], dim=1))


class DepthHead(nn.Module):
    """Features (B, C, h, w) -> depth (B, 1, H, W) in metres, between 0 and ``max_depth``: a 3x3
    ConvNormAct, a 1x1 convolution to one channel, resized to ``size`` and squashed with
    max_depth * sigmoid. Call it as head(features, image.shape[-2:])."""

    def __init__(self, in_channels: int, max_depth: float = 10.0, hidden_channels: int = 0) -> None:
        super().__init__()
        hidden = int(hidden_channels) or max(8, in_channels // 2)
        self.body = ConvNormAct(in_channels, hidden)
        self.out = nn.Conv2d(hidden, 1, 1)
        self.max_depth = float(max_depth)

    def forward(self, x: torch.Tensor, size: Sequence[int] | None = None) -> torch.Tensor:
        logits = self.out(self.body(x))
        if size is not None:
            logits = resize_to(logits, size)
        return self.max_depth * torch.sigmoid(logits)


# --- losses: (prediction, target, valid_mask) -> a scalar, over the valid pixels -----------------


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """The mean of ``values`` where ``mask`` is True; 0 (still a graph node) when none is."""
    if not bool(mask.any()):
        return values.sum() * 0.0
    return values[mask].mean()


def masked_l1(prediction: torch.Tensor, target: torch.Tensor, valid_mask: torch.Tensor) -> torch.Tensor:
    """The mean absolute error in metres over the valid pixels."""
    return _masked_mean((prediction - target).abs(), valid_mask)


def silog_loss(
    prediction: torch.Tensor,
    target: torch.Tensor,
    valid_mask: torch.Tensor,
    variance_focus: float = 0.85,
) -> torch.Tensor:
    """The scale-invariant log loss (Eigen et al. 2014) of most monocular depth work, over the
    valid pixels: sqrt(mean(d^2) - variance_focus * mean(d)^2) for d = log(pred) - log(target).
    ``variance_focus`` is from 0 to 1 (1 makes it fully scale-invariant)."""
    eps = 1e-6
    d = torch.log(prediction.clamp_min(eps)) - torch.log(target.clamp_min(eps))
    if not bool(valid_mask.any()):
        return d.sum() * 0.0
    d = d[valid_mask]
    variance = (d * d).mean() - float(variance_focus) * d.mean() ** 2
    return torch.sqrt(variance.clamp_min(0.0) + eps)


def gradient_loss(
    prediction: torch.Tensor, target: torch.Tensor, valid_mask: torch.Tensor
) -> torch.Tensor:
    """L1 between the horizontal and the vertical depth differences of neighbouring pixels, where
    both pixels are valid: sharp edges where the target has them."""
    pred_dx = prediction[..., :, 1:] - prediction[..., :, :-1]
    pred_dy = prediction[..., 1:, :] - prediction[..., :-1, :]
    true_dx = target[..., :, 1:] - target[..., :, :-1]
    true_dy = target[..., 1:, :] - target[..., :-1, :]
    mask_dx = valid_mask[..., :, 1:] & valid_mask[..., :, :-1]
    mask_dy = valid_mask[..., 1:, :] & valid_mask[..., :-1, :]
    return _masked_mean((pred_dx - true_dx).abs(), mask_dx) + _masked_mean(
        (pred_dy - true_dy).abs(), mask_dy
    )


def ssim_loss(
    prediction: torch.Tensor,
    target: torch.Tensor,
    valid_mask: torch.Tensor,
    window: int = 7,
    data_range: float = 10.0,
) -> torch.Tensor:
    """(1 - SSIM) / 2 over the valid pixels, from window x window local statistics; data_range is
    the depth range in metres. It rewards local structure that L1 misses."""
    window = max(3, int(window) | 1)  # odd, so the padding keeps the size

    def local(t: torch.Tensor) -> torch.Tensor:
        return F.avg_pool2d(t, window, stride=1, padding=window // 2, count_include_pad=False)

    c1, c2 = (0.01 * data_range) ** 2, (0.03 * data_range) ** 2
    mu_x, mu_y = local(prediction), local(target)
    var_x = local(prediction * prediction) - mu_x * mu_x
    var_y = local(target * target) - mu_y * mu_y
    cov = local(prediction * target) - mu_x * mu_y
    ssim = ((2 * mu_x * mu_y + c1) * (2 * cov + c2)) / (
        (mu_x * mu_x + mu_y * mu_y + c1) * (var_x + var_y + c2)
    )
    return _masked_mean((1 - ssim) / 2, valid_mask)
