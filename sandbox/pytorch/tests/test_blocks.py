"""The harness's blocks (harness.blocks) and shape trace (harness.trace), on the CPU in the sandbox
image: `make sandbox-test`, and CI's sandbox-image workflow. Plain unittest: the image has no
pytest."""

from __future__ import annotations

import unittest
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from harness import blocks
from harness.blocks import (
    ConvNormAct,
    CrossAttention,
    DepthHead,
    Encoder,
    FeatureAttention,
    GuidedUpsample,
    InvertedResidual,
    SqueezeExcite,
    UpBlock,
    gradient_loss,
    group_norm,
    masked_l1,
    resize_to,
    silog_loss,
    ssim_loss,
)
from harness.generated import ForwardFailed, ShapeMismatch, load_generated_loss, load_generated_model
from harness.trace import ShapeTrace, shape_of
from harness.train import _smoke_probe

EXAMPLES = Path("/opt/harness/examples")


class GroupNormTest(unittest.TestCase):
    def test_it_takes_the_most_groups_that_divide_the_channels(self) -> None:
        # The exit run's generated GroupNorm(32, 144) failed: 32 does not divide 144.
        self.assertEqual(group_norm(144).num_groups, 8)
        self.assertEqual(group_norm(36).num_groups, 6)
        self.assertEqual(group_norm(7).num_groups, 7)
        self.assertEqual(group_norm(13).num_groups, 1)
        self.assertEqual(group_norm(96, groups=32).num_groups, 32)
        self.assertEqual(group_norm(32, groups=1).num_groups, 1)


class BlockShapeTest(unittest.TestCase):
    def test_every_name_in_all_is_there(self) -> None:
        for name in blocks.__all__:
            self.assertTrue(callable(getattr(blocks, name)), name)

    def test_conv_norm_act_keeps_the_size_or_halves_it_rounding_up(self) -> None:
        x = torch.randn(2, 3, 15, 21)
        self.assertEqual(ConvNormAct(3, 8)(x).shape, (2, 8, 15, 21))
        self.assertEqual(ConvNormAct(3, 8, stride=2)(x).shape, (2, 8, 8, 11))
        self.assertEqual(ConvNormAct(3, 8, kernel_size=1, act="none")(x).shape, (2, 8, 15, 21))
        depthwise = ConvNormAct(8, 8, groups=8, act="gelu")
        self.assertEqual(depthwise(torch.randn(1, 8, 5, 5)).shape, (1, 8, 5, 5))
        with self.assertRaises(ValueError):
            ConvNormAct(3, 8, act="tanh")

    def test_inverted_residual_keeps_a_residual_only_when_the_shape_is_kept(self) -> None:
        x = torch.randn(2, 8, 9, 9)
        self.assertTrue(InvertedResidual(8, 8).residual)
        self.assertEqual(InvertedResidual(8, 8)(x).shape, x.shape)
        down = InvertedResidual(8, 12, stride=2, expand=1)
        self.assertFalse(down.residual)
        self.assertEqual(down(x).shape, (2, 12, 5, 5))

    def test_encoder_gives_one_map_per_stage_at_known_channels_and_strides(self) -> None:
        encoder = Encoder(channels=(8, 12, 16, 24, 32))
        features = encoder(torch.randn(2, 3, 61, 83))  # odd sizes round up at each stride
        self.assertEqual(encoder.channels, (8, 12, 16, 24, 32))
        self.assertEqual(encoder.strides, (2, 4, 8, 16, 32))
        self.assertEqual([f.shape[1] for f in features], [8, 12, 16, 24, 32])
        self.assertEqual(
            [tuple(f.shape[-2:]) for f in features], [(31, 42), (16, 21), (8, 11), (4, 6), (2, 3)]
        )
        with self.assertRaises(ValueError):
            Encoder(channels=(8, 16), depths=(1,))

    def test_attention_keeps_the_shape_and_lowers_heads_to_a_divisor(self) -> None:
        x = torch.randn(2, 12, 5, 7)
        attention = FeatureAttention(12, heads=8)
        self.assertEqual(attention.heads, 6)
        self.assertEqual(attention(x).shape, x.shape)
        self.assertEqual(FeatureAttention(12, heads=4, kv_stride=2)(x).shape, x.shape)

    def test_cross_attention_takes_a_feature_map_or_tokens(self) -> None:
        cross = CrossAttention(16, 24, heads=4)
        x = torch.randn(2, 16, 6, 8)
        self.assertEqual(cross(x, torch.randn(2, 24, 3, 4)).shape, x.shape)
        tokens = nn.Parameter(torch.zeros(1, 5, 24))  # learned tokens, shared by the batch
        self.assertEqual(cross(x, tokens).shape, x.shape)

    def test_squeeze_excite_keeps_the_shape(self) -> None:
        x = torch.randn(2, 12, 4, 4)
        self.assertEqual(SqueezeExcite(12)(x).shape, x.shape)

    def test_decoder_blocks_take_the_skip_or_guide_size_even_when_odd(self) -> None:
        up = UpBlock(16, 8, 12)
        self.assertEqual(up(torch.randn(2, 16, 4, 6), torch.randn(2, 8, 9, 13)).shape, (2, 12, 9, 13))
        guided = GuidedUpsample(12, 3, 8)
        self.assertEqual(
            guided(torch.randn(2, 12, 9, 13), torch.randn(2, 3, 35, 51)).shape, (2, 8, 35, 51)
        )

    def test_depth_head_is_positive_bounded_and_at_the_asked_size(self) -> None:
        head = DepthHead(16, max_depth=10.0)
        depth = head(torch.randn(2, 16, 15, 20) * 50, (61, 83))
        self.assertEqual(depth.shape, (2, 1, 61, 83))
        self.assertTrue(bool((depth >= 0).all()) and bool((depth <= 10).all()))
        self.assertEqual(head(torch.randn(1, 16, 4, 4)).shape, (1, 1, 4, 4))

    def test_resize_to_returns_the_same_tensor_at_the_same_size(self) -> None:
        x = torch.randn(1, 2, 3, 4)
        self.assertIs(resize_to(x, (3, 4)), x)
        self.assertEqual(resize_to(x, torch.Size([7, 9])).shape, (1, 2, 7, 9))


class LossTest(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(0)
        self.target = torch.rand(2, 1, 16, 16) * 5 + 0.5
        self.mask = torch.rand(2, 1, 16, 16) > 0.2

    def test_a_perfect_prediction_costs_nothing(self) -> None:
        t, m = self.target, self.mask
        self.assertEqual(float(masked_l1(t, t, m)), 0.0)
        self.assertEqual(float(gradient_loss(t, t, m)), 0.0)
        self.assertLess(float(silog_loss(t, t, m)), 1e-2)
        self.assertLess(float(ssim_loss(t, t, m)), 1e-4)

    def test_invalid_pixels_are_left_out(self) -> None:
        prediction = torch.where(self.mask, self.target + 1.0, torch.full_like(self.target, 100.0))
        self.assertAlmostEqual(float(masked_l1(prediction, self.target, self.mask)), 1.0, places=5)

    def test_silog_with_full_focus_ignores_a_global_scale(self) -> None:
        loss = silog_loss(self.target * 2, self.target, self.mask, variance_focus=1.0)
        self.assertLess(float(loss), 1e-2)
        self.assertGreater(float(silog_loss(self.target * 2, self.target, self.mask)), 0.2)

    def test_no_valid_pixel_gives_zero_and_keeps_the_graph(self) -> None:
        prediction = torch.rand(1, 1, 8, 8, requires_grad=True)
        none = torch.zeros(1, 1, 8, 8, dtype=torch.bool)
        for loss in (masked_l1, silog_loss, gradient_loss, ssim_loss):
            value = loss(prediction, self.target[:1, :, :8, :8], none)
            self.assertEqual(float(value.detach()), 0.0, loss.__name__)
            value.backward()


class ExampleTest(unittest.TestCase):
    def test_the_blocks_example_loads_trains_a_step_and_keeps_the_shape(self) -> None:
        # Through the generated-code loader: the checker passes it, and the harness builds it.
        model = load_generated_model(EXAMPLES / "depth_blocks", {"base_channels": 8})
        loss_fn = load_generated_loss(EXAMPLES / "depth_blocks")
        image = torch.rand(2, 3, 48, 64)
        target = torch.rand(2, 1, 48, 64) * 9 + 0.5
        prediction = model(image)
        self.assertEqual(prediction.shape, target.shape)
        loss = loss_fn(prediction, target, target > 1e-3)
        self.assertTrue(bool(torch.isfinite(loss)))
        loss.backward()
        self.assertTrue(all(p.grad is not None for p in model.parameters() if p.requires_grad))


class ShapeTraceTest(unittest.TestCase):
    def test_a_failed_pass_names_where_it_failed_and_with_which_shapes(self) -> None:
        model = load_generated_model(EXAMPLES / "wrong_channels", {})
        with ShapeTrace(model) as trace, self.assertRaises(RuntimeError):
            model(torch.rand(1, 3, 32, 32))
        report = trace.report()
        self.assertIn(
            "The forward pass failed inside: Model (Model) > up (UpBlock) > up.fuse (Sequential) "
            "> up.fuse.0 (ConvNormAct) > up.fuse.0.conv (Conv2d)",
            report,
        )
        self.assertIn("whose inputs were: (1, 56, 8, 8)", report)  # 32 + 24 channels, not 64
        self.assertIn(
            "encoder (Encoder): (1, 3, 32, 32) -> [(1, 16, 16, 16), (1, 24, 8, 8), (1, 32, 4, 4)]",
            report,
        )

    def test_the_hooks_go_when_the_block_ends(self) -> None:
        model = Encoder(channels=(8, 12), depths=(1, 1))
        with ShapeTrace(model):
            model(torch.rand(1, 3, 8, 8))
        for module in model.modules():
            self.assertFalse(module._forward_hooks or module._forward_pre_hooks)

    def test_shapes_of_other_values(self) -> None:
        self.assertEqual(shape_of(None), "None")
        self.assertEqual(shape_of(3), "3")
        self.assertEqual(shape_of({"a": torch.zeros(2)}), "{a: (2,)}")
        self.assertEqual(shape_of([torch.zeros(1)] * 8), "[" + ", ".join(["(1,)"] * 6) + ", ... 8 in all]")


class SmokeProbeTest(unittest.TestCase):
    def loader(self) -> DataLoader:
        images, depths = torch.rand(2, 3, 32, 32), torch.rand(2, 1, 32, 32) + 0.5
        return DataLoader(TensorDataset(images, depths), batch_size=2)

    def loss(self) -> object:
        return lambda prediction, target: (prediction - target).abs().mean()

    def test_a_forward_that_raises_is_reported_with_its_trace(self) -> None:
        model = load_generated_model(EXAMPLES / "wrong_channels", {})
        with self.assertRaises(ForwardFailed) as raised:
            _smoke_probe(model, self.loss, self.loader(), torch.device("cpu"))
        self.assertEqual(raised.exception.error_code, "train.error")
        message = str(raised.exception)
        self.assertTrue(message.startswith("RuntimeError: "), message)
        self.assertIn("The forward pass failed inside: Model (Model) > up (UpBlock)", message)

    def test_a_wrong_output_shape_is_reported_with_the_trace_too(self) -> None:
        model = nn.Sequential(ConvNormAct(3, 1, stride=2))  # half the size
        with self.assertRaises(ShapeMismatch) as raised:
            _smoke_probe(model, self.loss, self.loader(), torch.device("cpu"))
        message = str(raised.exception)
        self.assertIn("does not match target (2, 1, 32, 32)", message)
        self.assertIn("Model (Sequential): (2, 3, 32, 32) -> (2, 1, 16, 16)", message)


if __name__ == "__main__":
    unittest.main()
