/**
 * Test-only: one consistent demo story, made by the worker's demo generators (agentic_core.demo:
 * topic "Monocular depth estimation on NYU Depth v2", seed 7, RunConfig(max_papers=5)), with long
 * texts shortened. Plus small builders for the API shapes that carry stage outputs.
 */
import type {
  CodingOutput,
  ExperimentOutput,
  LiteratureOutput,
  MethodOutput,
  OutputVersionOut,
  RunDetail,
  StageAttemptOut,
  StageDetail,
  StageOutputOut,
  StageRunOut,
  WritingOutput,
} from "@/client";
import type { StageOutputData } from "./stage-output";

export const DEMO_LITERATURE: LiteratureOutput = {
  plan: {
    topic: "Monocular depth estimation on NYU Depth v2",
    queries: [
      "monocular depth estimation on NYU depth v2",
      "monocular depth estimation on NYU depth v2 geometric priors",
      "diffusion priors for monocular depth estimation",
      "monocular depth estimation NYU Depth V2 benchmark",
    ],
    scope:
      "Learning-based monocular depth estimation on NYU depth v2 methods published between 2018 and 2026, with emphasis on geometric priors and diffusion priors. Hand-crafted pipelines and papers without a quantitative evaluation are out of scope.",
    inclusion_criteria: [
      "Published between 2018 and 2026",
      "Proposes or evaluates a learning-based method for monocular depth estimation on NYU depth v2",
      "Reports quantitative results on a public benchmark such as NYU Depth V2",
      "Peer-reviewed, or an arXiv preprint with enough detail to reproduce",
    ],
    subtopics: [
      "Geometric priors",
      "Diffusion priors",
      "Self-supervised learning",
      "Scale ambiguity",
    ],
  },
  papers: [
    {
      paper_id: "arxiv:1904.96234",
      title: "Revisiting Monocular Depth Estimation on NYU Depth v2: A Large-Scale Benchmark",
      authors: ["Camila Hernández", "Kofi Diallo"],
      year: 2019,
      venue: "AAAI",
      doi: "10.5555/aaai.2019.98727",
      arxiv_id: "1904.96234",
      url: "https://arxiv.org/abs/1904.96234",
      abstract:
        "Monocular depth estimation on NYU depth v2 remains difficult because of unseen camera intrinsics. We introduce GeoDiff, an uncertainty-aware model built on state space models and a scale-invariant objective. An auxiliary surface-normal head regularizes the predicted geometry. On SUN RGB-D, GeoDiff reduces RMSE by 16.5% relative to the strongest baseline. Ablations attribute most of the improvement to the scale-invariant objective.",
      citation_count: null,
      source: "arxiv",
      pdf_available: true,
      relevance: 0.74,
      decision: "include",
      decision_reason:
        "Proposes state space models for monocular depth estimation on NYU depth v2 and reports RMSE on SUN RGB-D.",
    },
    {
      paper_id: "arxiv:2506.94418",
      title:
        "When Does Multi-Scale Feature Fusion Help Monocular Depth Estimation on NYU Depth v2?",
      authors: ["Jing Wang", "Ruoxi Liu", "Ruoxi Wang", "Xin Yang", "Xin Chen", "Haoran Huang"],
      year: 2025,
      venue: "ICML",
      doi: "10.5555/icml.2025.90587",
      arxiv_id: "2506.94418",
      url: "https://arxiv.org/abs/2506.94418",
      abstract:
        "Most monocular depth estimation on NYU depth v2 methods are tuned on a single benchmark, which hides their sensitivity to thin structures and depth discontinuities. We propose NOVA, which combines multi-scale feature fusion with a multi-scale decoder. Training mixes labeled indoor scenes with pseudo-labeled video frames. Experiments on KITTI show a 11.7% gain in RMSE over prior work with 34.2M parameters. The model trains on a single consumer GPU in under 13 hours.",
      citation_count: 32,
      source: "arxiv",
      pdf_available: true,
      relevance: 0.73,
      decision: "include",
      decision_reason:
        "Proposes multi-scale feature fusion for monocular depth estimation on NYU depth v2 and reports RMSE on KITTI.",
    },
    {
      paper_id: "arxiv:2412.99517",
      title: "When Does Synthetic Data Help Monocular Depth Estimation on NYU Depth v2?",
      authors: [
        "Jiahui Chen",
        "Tomas Dvorak",
        "Clara Novak",
        "Ruoxi Liu",
        "Jing Zhang",
        "Tianyi Wu",
      ],
      year: 2024,
      venue: "IEEE TIP",
      doi: "10.5555/ieeetip.2024.94516",
      arxiv_id: "2412.99517",
      url: "https://openalex.org/W9471417056",
      abstract:
        "Despite rapid progress, monocular depth estimation on NYU depth v2 models still struggle with the gap between synthetic and real indoor scenes. We introduce DepthNet-XL, an efficient model built on synthetic data and a multi-scale decoder. Training mixes labeled indoor scenes with pseudo-labeled video frames. DepthNet-XL reaches AbsRel 0.109 on NYU Depth V2 while running at 21 FPS on a single GPU. The model trains on a single consumer GPU in under 24 hours.",
      citation_count: null,
      source: "openalex",
      pdf_available: true,
      relevance: 0.72,
      decision: "include",
      decision_reason:
        "Directly addresses the gap between synthetic and real indoor scenes, with a reproducible evaluation on NYU Depth V2.",
    },
    {
      paper_id: "arxiv:2007.95851",
      title: "Robust Monocular Depth Estimation on NYU Depth v2",
      authors: ["Yui Suzuki", "Kenji Nakamura", "Dilnoza Karimova"],
      year: 2020,
      venue: "ICML",
      doi: "10.5555/icml.2020.90605",
      arxiv_id: "2007.95851",
      url: "https://openalex.org/W9503048443",
      abstract:
        "Most monocular depth estimation on NYU depth v2 methods are tuned on a single benchmark, which hides their sensitivity to low-light images. We propose DepthFormer, which combines multi-scale feature fusion with a scale-invariant objective. A learned global scale token recovers metric depth from relative predictions. DepthFormer reaches AbsRel 0.135 on NYU Depth V2 while running at 88 FPS on a single GPU. Code and trained weights are publicly available.",
      citation_count: null,
      source: "openalex",
      pdf_available: true,
      relevance: 0.69,
      decision: "maybe",
      decision_reason: "Promising, but the training details and evaluation protocol are missing.",
    },
    {
      paper_id: "arxiv:2306.94263",
      title: "NOVA-Plus: Scale-Aware Monocular Depth Estimation on NYU Depth v2 at Scale",
      authors: [
        "Mateo Gómez",
        "Lucía Morales",
        "Yui Takahashi",
        "Valentina Rodríguez",
        "Priya Iyer",
        "Camila Fernández",
      ],
      year: 2023,
      venue: "3DV Workshops",
      doi: "10.5555/3dvworkshops.2023.90215",
      arxiv_id: "2306.94263",
      url: "https://openalex.org/W9167866968",
      abstract:
        "Despite rapid progress, monocular depth estimation on NYU depth v2 models still struggle with reflective and textureless surfaces. We propose NOVA-Plus, which combines uncertainty estimation with a lightweight uncertainty branch. Training mixes labeled indoor scenes with pseudo-labeled video frames.",
      citation_count: 52,
      source: "openalex",
      pdf_available: true,
      relevance: 0.35,
      decision: "exclude",
      decision_reason: "Two-page workshop abstract without enough detail to assess the method.",
    },
  ],
  analyses: [
    {
      paper_id: "arxiv:1904.96234",
      contribution:
        "Introduces GeoDiff, which applies state space models to monocular depth estimation on NYU depth v2 with a scale-invariant objective.",
      method:
        "An EfficientNet-B3 encoder with a scale-invariant objective, trained end to end on SUN RGB-D for 25 epochs (learning rate 3e-4).",
      results: "Reports RMSE 0.394 on SUN RGB-D, 16.5% lower than the strongest baseline.",
      limitations: "Assumes known camera intrinsics at test time.",
      evidence: [
        {
          quote: "The EfficientNet-B3 encoder is initialized from ImageNet-pretrained weights.",
          page: 5,
        },
      ],
    },
    {
      paper_id: "arxiv:2506.94418",
      contribution:
        "Introduces NOVA, which applies multi-scale feature fusion to monocular depth estimation on NYU depth v2 with a multi-scale decoder.",
      method:
        "A ResNet-50 encoder with a multi-scale decoder, trained end to end on KITTI for 30 epochs (learning rate 3e-4).",
      results: "Reports RMSE 0.413 on KITTI, 11.7% lower than the strongest baseline.",
      limitations: "Needs a large teacher network at training time.",
      evidence: [
        {
          quote: "The ResNet-50 encoder is initialized from ImageNet-pretrained weights.",
          page: 4,
        },
      ],
    },
    {
      paper_id: "arxiv:2412.99517",
      contribution:
        "Introduces DepthNet-XL, which applies synthetic data to monocular depth estimation on NYU depth v2 with a multi-scale decoder.",
      method:
        "A ConvNeXt-T encoder with a multi-scale decoder, trained end to end on NYU Depth V2 for 30 epochs (learning rate 3e-4).",
      results: "Reports AbsRel 0.109 on NYU Depth V2, 10.0% lower than the strongest baseline.",
      limitations: "Errors grow sharply for surfaces farther than 8 m.",
      evidence: [
        {
          quote: "On NYU Depth V2, DepthNet-XL achieves AbsRel of 0.109.",
          page: 6,
        },
      ],
    },
  ],
  key_findings: [
    {
      title: "Revisiting Monocular Depth Estimation on NYU Depth v2: A Large-Scale Benchmark",
      source: "arXiv",
      summary:
        "GeoDiff shows that state space models improves robustness to unseen camera intrinsics (RMSE 0.394 on SUN RGB-D).",
      url: "https://arxiv.org/abs/1904.96234",
      paper_id: "arxiv:1904.96234",
    },
    {
      title:
        "When Does Multi-Scale Feature Fusion Help Monocular Depth Estimation on NYU Depth v2?",
      source: "arXiv",
      summary:
        "NOVA shows that multi-scale feature fusion transfers to unseen scenes without fine-tuning (RMSE 0.413 on KITTI).",
      url: "https://arxiv.org/abs/2506.94418",
      paper_id: "arxiv:2506.94418",
    },
  ],
  synthesis:
    "The search screened 5 papers on monocular depth estimation on NYU depth v2 published between 2019 and 2025 and kept 3 for full reading. Two lines of work dominate: state space models and multi-scale feature fusion. GeoDiff and NOVA report the largest gains: 16.5% in RMSE on SUN RGB-D and 11.7% in RMSE on KITTI.\n\nEvidence is thinner for reflective and textureless surfaces: only 1 of the 3 included papers evaluates it explicitly. Reported numbers are also hard to compare, because the papers differ in splits, input resolution and evaluation protocol. The most common limitation in the reading notes is: Inference speed on embedded hardware is not reported.\n\nFor the method stage, the most promising direction is to combine state space models with a lightweight uncertainty branch in a model small enough for a 6 GB GPU, and to evaluate it on NYU Depth V2 with AbsRel, RMSE and δ1.",
};

export const DEMO_METHOD: MethodOutput = {
  research_gaps: [
    "Real-time inference on consumer GPUs with 6 GB of memory",
    "Sharp depth discontinuities at object boundaries",
    "Robustness on reflective and transparent surfaces",
    "Only 1 of the 3 included papers reports results on more than one dataset",
  ],
  proposals: [
    {
      name: "Edge-preserving multi-scale decoder with SILog and gradient losses",
      rationale:
        "Several included papers attribute their gains at object boundaries to multi-scale fusion and gradient-matching terms, both cheap to add to a compact encoder-decoder. Supported by 3 screened papers.",
      expected_benefit: "Sharper depth discontinuities and a better AbsRel on NYU Depth V2.",
      risk: "Gradient terms can amplify sensor noise around invalid pixels.",
      evidence_paper_ids: ["arxiv:1904.96234", "arxiv:2506.94418", "arxiv:2412.99517"],
    },
    {
      name: "Lightweight state-space encoder for long-range context",
      rationale:
        "Recent work suggests state-space blocks capture global scene layout at a lower memory cost than attention, which matters on a 6 GB GPU. Supported by one screened paper.",
      expected_benefit:
        "Global context within the memory budget and a lower AbsRel on NYU Depth V2.",
      risk: "Few reference implementations exist, and training may be unstable.",
      evidence_paper_ids: ["arxiv:2412.99517"],
    },
    {
      name: "Scale-aware distillation from a frozen foundation teacher",
      rationale:
        "Depth foundation models generalize well but are too heavy for the lab's GPU. Distilling their relative depth plus a learned global scale into a small student keeps most of the accuracy at a fraction of the cost. Supported by 3 screened papers.",
      expected_benefit:
        "Lower AbsRel on NYU Depth V2 than a student trained from scratch, with fewer than 15M parameters.",
      risk: "Teacher errors on reflective surfaces transfer to the student.",
      evidence_paper_ids: ["arxiv:1904.96234", "arxiv:2506.94418", "arxiv:2412.99517"],
    },
  ],
  recommended_option: "Scale-aware distillation from a frozen foundation teacher",
  implementation_focus:
    "Implement scale-aware distillation from a frozen foundation teacher as a compact U-Net-style encoder-decoder that trains on the lab's 6 GB GTX 1060 with mixed precision. Keep the harness-owned NYU Depth V2 loader, metrics and training loop, generate only the model and loss modules, and report AbsRel and RMSE.",
  datasets: ["nyu2"],
  evaluation_metrics: ["abs_rel", "rmse"],
};

export const DEMO_CODING: CodingOutput = {
  summary:
    "Scale-aware distillation from a frozen foundation teacher: DepthNet, a 4-stage U-Net-style encoder-decoder with about 4.4M parameters, trained with scale-invariant logarithmic (SILog) loss. The smoke test passed: 4 unit tests and a 2-batch dry run on the NVIDIA GeForce GTX 1060 6GB in 31 s.",
  files: [
    {
      path: "model.py",
      language: "python",
      role: "model",
      content:
        '"""DepthNet: Scale-aware distillation from a frozen foundation teacher.\n\nGenerated by the coding stage for monocular depth estimation on NYU Depth V2.\nThe experiment harness owns the data loader, the metrics and the training loop;\nthis module only defines the network.\n"""\n',
    },
    {
      path: "losses.py",
      language: "python",
      role: "loss",
      content:
        '"""Training objective for DepthNet: SILog loss plus a gradient-matching term."""\n\nfrom __future__ import annotations\n\nimport torch\nfrom torch import nn\n',
    },
    {
      path: "configs/train.yaml",
      language: "yaml",
      role: "config",
      content:
        '# Experiment config for "Scale-aware distillation from a frozen foundation teacher" (attempt 1).\n# The harness validates every value against its bounds before the job starts.\ntask: nyu2_depth\nseed: 7\nrequire_gpu: true\nmodel:\n',
    },
    {
      path: "tests/test_model.py",
      language: "python",
      role: "test",
      content:
        '"""Unit tests the smoke test runs before any GPU time is spent."""\n\nimport torch\n\nfrom losses import DepthLoss\nfrom model import DepthNet\n',
    },
    {
      path: "README.md",
      language: "markdown",
      role: "docs",
      content:
        "# DepthNet: Scale-aware distillation from a frozen foundation teacher\n\nImplements the method stage's recommendation, **Scale-aware distillation from a frozen foundation teacher**, for monocular depth estimation on NYU Depth V2. The sandbox harness owns the data loader, the metrics and the training loop; this package only adds the model and the loss.\n\n## Files\n\n",
    },
  ],
  entrypoint: "model.py:DepthNet",
  smoke_test: {
    passed: true,
    duration_seconds: 31.3,
    log: "$ python -m pytest -q tests/test_model.py\n....                                                                     [100%]\n4 passed in 8.28s\n",
  },
};

export const DEMO_EXPERIMENT: ExperimentOutput = {
  status: "succeeded",
  summary:
    "Trained DepthNet for 24 epochs on NYU Depth V2 (19 GPU-minutes on the NVIDIA GeForce GTX 1060 6GB). Validation AbsRel went from 0.478 to 0.157; the best validation loss, 0.5401, came at epoch 23.",
  config: {
    model: "DepthNet",
    dataset: "nyu2",
    input_size: "[480, 640]",
    batch_size: 8,
    epochs: 24,
    optimizer: "adamw",
    learning_rate: 0.0002,
    weight_decay: 0.0001,
    scheduler: "cosine",
    warmup_epochs: 1,
    amp: true,
    seed: 7,
  },
  series: [
    {
      name: "loss",
      split: "train",
      higher_is_better: false,
      points: [
        {
          epoch: 0,
          value: 2.2504,
        },
        {
          epoch: 1,
          value: 2.003,
        },
        {
          epoch: 2,
          value: 1.7484,
        },
        {
          epoch: 3,
          value: 1.5287,
        },
        {
          epoch: 4,
          value: 1.3299,
        },
        {
          epoch: 5,
          value: 1.2091,
        },
        {
          epoch: 6,
          value: 1.0907,
        },
        {
          epoch: 7,
          value: 0.9674,
        },
        {
          epoch: 8,
          value: 0.872,
        },
        {
          epoch: 9,
          value: 0.8233,
        },
        {
          epoch: 10,
          value: 0.7335,
        },
        {
          epoch: 11,
          value: 0.6622,
        },
        {
          epoch: 12,
          value: 0.6074,
        },
        {
          epoch: 13,
          value: 0.5899,
        },
        {
          epoch: 14,
          value: 0.546,
        },
        {
          epoch: 15,
          value: 0.5156,
        },
        {
          epoch: 16,
          value: 0.4888,
        },
        {
          epoch: 17,
          value: 0.4742,
        },
        {
          epoch: 18,
          value: 0.4256,
        },
        {
          epoch: 19,
          value: 0.4403,
        },
        {
          epoch: 20,
          value: 0.4114,
        },
        {
          epoch: 21,
          value: 0.3977,
        },
        {
          epoch: 22,
          value: 0.3843,
        },
        {
          epoch: 23,
          value: 0.377,
        },
      ],
    },
    {
      name: "loss",
      split: "val",
      higher_is_better: false,
      points: [
        {
          epoch: 0,
          value: 2.2919,
        },
        {
          epoch: 1,
          value: 1.7547,
        },
        {
          epoch: 2,
          value: 1.8214,
        },
        {
          epoch: 3,
          value: 1.5577,
        },
        {
          epoch: 4,
          value: 1.6192,
        },
        {
          epoch: 5,
          value: 1.3384,
        },
        {
          epoch: 6,
          value: 1.2502,
        },
        {
          epoch: 7,
          value: 1.0757,
        },
        {
          epoch: 8,
          value: 1.0933,
        },
        {
          epoch: 9,
          value: 0.938,
        },
        {
          epoch: 10,
          value: 0.93,
        },
        {
          epoch: 11,
          value: 0.8372,
        },
        {
          epoch: 12,
          value: 0.7935,
        },
        {
          epoch: 13,
          value: 0.7451,
        },
        {
          epoch: 14,
          value: 0.712,
        },
        {
          epoch: 15,
          value: 0.6558,
        },
        {
          epoch: 16,
          value: 0.6126,
        },
        {
          epoch: 17,
          value: 0.6236,
        },
        {
          epoch: 18,
          value: 0.5845,
        },
        {
          epoch: 19,
          value: 0.553,
        },
        {
          epoch: 20,
          value: 0.5955,
        },
        {
          epoch: 21,
          value: 0.5885,
        },
        {
          epoch: 22,
          value: 0.5437,
        },
        {
          epoch: 23,
          value: 0.5401,
        },
      ],
    },
    {
      name: "abs_rel",
      split: "val",
      higher_is_better: false,
      points: [
        {
          epoch: 0,
          value: 0.4781,
        },
        {
          epoch: 1,
          value: 0.4461,
        },
        {
          epoch: 2,
          value: 0.3951,
        },
        {
          epoch: 3,
          value: 0.3292,
        },
        {
          epoch: 4,
          value: 0.3239,
        },
        {
          epoch: 5,
          value: 0.299,
        },
        {
          epoch: 6,
          value: 0.2852,
        },
        {
          epoch: 7,
          value: 0.2556,
        },
        {
          epoch: 8,
          value: 0.2527,
        },
        {
          epoch: 9,
          value: 0.2384,
        },
        {
          epoch: 10,
          value: 0.2254,
        },
        {
          epoch: 11,
          value: 0.2082,
        },
        {
          epoch: 12,
          value: 0.2013,
        },
        {
          epoch: 13,
          value: 0.1935,
        },
        {
          epoch: 14,
          value: 0.19,
        },
        {
          epoch: 15,
          value: 0.1794,
        },
        {
          epoch: 16,
          value: 0.1777,
        },
        {
          epoch: 17,
          value: 0.1722,
        },
        {
          epoch: 18,
          value: 0.17,
        },
        {
          epoch: 19,
          value: 0.1583,
        },
        {
          epoch: 20,
          value: 0.1657,
        },
        {
          epoch: 21,
          value: 0.1635,
        },
        {
          epoch: 22,
          value: 0.1613,
        },
        {
          epoch: 23,
          value: 0.1569,
        },
      ],
    },
    {
      name: "rmse",
      split: "val",
      higher_is_better: false,
      points: [
        {
          epoch: 0,
          value: 1.7155,
        },
        {
          epoch: 1,
          value: 1.4544,
        },
        {
          epoch: 2,
          value: 1.3468,
        },
        {
          epoch: 3,
          value: 1.238,
        },
        {
          epoch: 4,
          value: 1.2185,
        },
        {
          epoch: 5,
          value: 1.0726,
        },
        {
          epoch: 6,
          value: 1.0304,
        },
        {
          epoch: 7,
          value: 0.9317,
        },
        {
          epoch: 8,
          value: 0.8653,
        },
        {
          epoch: 9,
          value: 0.813,
        },
        {
          epoch: 10,
          value: 0.8063,
        },
        {
          epoch: 11,
          value: 0.7428,
        },
        {
          epoch: 12,
          value: 0.7215,
        },
        {
          epoch: 13,
          value: 0.6905,
        },
        {
          epoch: 14,
          value: 0.6992,
        },
        {
          epoch: 15,
          value: 0.6924,
        },
        {
          epoch: 16,
          value: 0.6335,
        },
        {
          epoch: 17,
          value: 0.6229,
        },
        {
          epoch: 18,
          value: 0.619,
        },
        {
          epoch: 19,
          value: 0.6329,
        },
        {
          epoch: 20,
          value: 0.589,
        },
        {
          epoch: 21,
          value: 0.6103,
        },
        {
          epoch: 22,
          value: 0.6028,
        },
        {
          epoch: 23,
          value: 0.5734,
        },
      ],
    },
  ],
  final_metrics: {
    abs_rel: 0.1569,
    rmse: 0.5734,
    val_loss: 0.5401,
    train_loss: 0.377,
  },
  logs_tail:
    "2026-10-30 02:57:37,971 INFO epoch 21 step 0 loss 0.3553\n2026-10-30 02:57:46,021 INFO epoch 21 step 400 loss 0.4127\n2026-10-30 02:57:54,071 INFO epoch 21 step 800 loss 0.4053\n",
  provenance: {
    image_digest: "sha256:b415e5fee28feb439c1b68314e9949b590261650ec1a5b70c60d8e44abdb8d7c",
    code_sha256: "d01cd659593663d5cfe1c4893ca4c508d31984301bc13ec64ea5182295e2e8db",
    config_sha256: "374d56c0f1101b957b8c347cacde0bdbbe5cede1e09928107994ccd1c6805772",
    dataset: "nyu2",
    dataset_version: "2025.03",
    seed: 7,
    gpu_name: "NVIDIA GeForce GTX 1060 6GB",
    gpu_seconds: 1136.5,
    started_at: "2026-10-30T02:40:32.196827Z",
    finished_at: "2026-10-30T03:00:00Z",
  },
};

export const DEMO_WRITING: WritingOutput = {
  title:
    "Monocular Depth Estimation on NYU Depth v2: Scale-Aware Distillation from a Frozen Foundation Teacher",
  abstract:
    "Monocular depth estimation on NYU depth v2 underpins robot navigation, augmented reality and 3D scene understanding, yet published systems are hard to reproduce on modest hardware. Building on 3 papers kept by a structured literature review, we study scale-aware distillation from a frozen foundation teacher. The model, DepthNet, is a compact U-Net-style encoder-decoder trained with scale-invariant logarithmic (SILog) loss on NYU Depth V2. In a 24-epoch run on a single NVIDIA GeForce GTX 1060 6GB, it reaches AbsRel 0.157 and RMSE 0.573 on the validation split. We describe the method, the training protocol and its provenance record, and discuss real-time inference on consumer GPUs with 6 GB of memory as the main open problem. All numbers come from one seeded run and need repeated seeds before any claim is final.",
  markdown:
    "# Monocular Depth Estimation on NYU Depth v2: Scale-Aware Distillation from a Frozen Foundation Teacher\n\n## Abstract\n\nMonocular depth estimation on NYU depth v2 underpins robot navigation, augmented reality and 3D scene understanding, yet published systems are hard to reproduce on modest hardware. Building on 3 papers kept by a structured literature review, we study scale-aware distillation from a frozen foundation teacher. The model, DepthNet, is a compact U-Net-style encoder-decoder trained with scale-invariant logarithmic (SILog) loss on NYU Depth V2. In a 24-epoch run on a single NVIDIA GeForce GTX 1060 6GB, it reaches AbsRel 0.157 and RMSE 0.573 on the validation split. We describe the method, the training protocol and its provenance record, and discuss real-time inference on consumer GPUs with 6 GB of memory as the main open problem. All numbers come from one seeded run and need repeated seeds before any claim is final.\n\n## 1. Introduction\n\nMonocular depth estimation on NYU depth v2 has advanced quickly. Recent models produce convincing predictions on standard benchmarks [1], and knowledge distillation has become a common ingredient [2]. Yet most published systems assume training budgets far beyond a single consumer GPU, and their reported gains are hard to compare because papers differ in splits, input resolution and evaluation protocol [3]. A small lab therefore cannot tell which ideas will survive its own constraints.\n\nThis draft follows the recommendation of the method stage, scale-aware distillation from a frozen foundation teacher. The goal is a model that one NVIDIA GeForce GTX 1060 6GB can train in about an hour while staying competitive on NYU Depth V2. Our contributions are:\n\n- DepthNet, a compact U-Net-style encoder-decoder trained with scale-invariant logarithmic (SILog) loss, generated and unit-tested in a sandbox.\n- A seeded training run on NYU Depth V2 with a complete provenance record: image digest, code and config hashes, dataset version.\n- An analysis of the remaining gap, real-time inference on consumer GPUs with 6 GB of memory, grounded in the 5 screened papers.\n",
  sections: [
    {
      name: "Abstract",
      objective: "Summarize the problem, the method and the main result in one paragraph.",
    },
    {
      name: "Introduction",
      objective: "Motivate the problem, state the gap and list the contributions.",
    },
    {
      name: "Related Work",
      objective: "Position the work against the papers kept by the literature stage.",
    },
    {
      name: "Method",
      objective: "Describe the model and the training objective.",
    },
    {
      name: "Experiments",
      objective: "Report the setup, the provenance and the final metrics.",
    },
    {
      name: "Discussion",
      objective: "Interpret the results and state the limitations honestly.",
    },
    {
      name: "Conclusion",
      objective: "Summarize the findings and the next steps.",
    },
    {
      name: "References",
      objective: "List every cited paper with its venue and year.",
    },
  ],
  citations: [
    {
      key: 1,
      paper_id: "arxiv:1904.96234",
    },
    {
      key: 2,
      paper_id: "arxiv:2506.94418",
    },
    {
      key: 3,
      paper_id: "arxiv:2412.99517",
    },
  ],
  output_format: "Markdown draft with the structure of an IEEE conference paper",
  review_focus:
    "Check that every [n] citation supports its claim and that the results table matches the experiment's final metrics.",
};

/** Every stage's demo output, keyed by stage. */
export const DEMO_OUTPUTS: StageOutputData = {
  literature: DEMO_LITERATURE,
  method: DEMO_METHOD,
  coding: DEMO_CODING,
  experiment: DEMO_EXPERIMENT,
  writing: DEMO_WRITING,
};

let counter = 0;

/** A fresh, valid-looking UUID (deterministic within a test file). */
export function nextId(): string {
  counter += 1;
  return `00000000-0000-4000-8000-${String(counter).padStart(12, "0")}`;
}

/** A sha256 hex digest that differs per call. */
export function nextSha(): string {
  counter += 1;
  return counter.toString(16).padStart(64, "0");
}

/** One output version as GET /runs/{id}/stages/{stage} lists it. */
export function versionOut(
  data: Record<string, unknown>,
  overrides: Partial<OutputVersionOut> = {},
): OutputVersionOut {
  return {
    id: nextId(),
    version: 1,
    sha256: nextSha(),
    data,
    degraded: true,
    degraded_reason: "stage.demo",
    model: null,
    prompt_version: "demo@1",
    edited_by: null,
    edited_by_name: null,
    created_at: "2026-10-30T01:00:00Z",
    schema_ok: true,
    approval: null,
    ...overrides,
  };
}

/** One attempt of a stage with its versions. */
export function attemptOut(
  attempt: number,
  outputs: OutputVersionOut[],
  overrides: Partial<StageAttemptOut> = {},
): StageAttemptOut {
  return {
    id: nextId(),
    attempt,
    status: "output_ready",
    feedback: null,
    error: null,
    started_at: `2026-10-30T0${attempt}:00:00Z`,
    finished_at: null,
    outputs,
    ...overrides,
  };
}

export function stageDetailOut(
  runId: string,
  stage: string,
  attempts: StageAttemptOut[],
): StageDetail {
  return { run_id: runId, stage, attempts };
}

/** An output as the run detail carries it (no schema check, no approval). */
export function stageOutputOut(
  data: Record<string, unknown>,
  overrides: Partial<StageOutputOut> = {},
): StageOutputOut {
  return {
    id: nextId(),
    version: 1,
    data,
    sha256: nextSha(),
    model: null,
    degraded: true,
    degraded_reason: "stage.demo",
    created_at: "2026-10-30T01:00:00Z",
    ...overrides,
  };
}

export function stageRunOut(
  stage: string,
  status: StageRunOut["status"],
  overrides: Partial<StageRunOut> = {},
): StageRunOut {
  return {
    id: nextId(),
    stage,
    attempt: 1,
    status,
    feedback: null,
    error: null,
    started_at: "2026-10-30T00:00:00Z",
    finished_at: null,
    outputs: [],
    ...overrides,
  };
}

export function runDetailOut(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    project_id: "33333333-3333-4333-8333-333333333333",
    owner_id: "owner",
    topic: "Monocular depth estimation on NYU Depth v2",
    status: "running",
    llm_policy: "auto",
    budget_cap_usd: null,
    config: {
      year_from: 2018,
      year_to: 2026,
      sources: ["arxiv", "semantic_scholar", "openalex"],
      max_papers: 5,
      stages: ["literature", "method", "coding", "experiment", "writing"],
      dataset: "nyu2",
    },
    error: null,
    created_at: "2026-10-30T00:00:00Z",
    updated_at: "2026-10-30T01:00:00Z",
    stages: [],
    awaiting: null,
    awaiting_stage: null,
    can_steer: true,
    ...overrides,
  };
}
