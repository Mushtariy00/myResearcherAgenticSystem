"""Research domains the demo generators imitate: datasets, metrics, vocabulary and losses.

A known dataset picks the domain, because the experiment runs on it; otherwise words in the
topic do. Monocular depth on NYU Depth V2 (the lab's registered dataset) is the default.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    id: str  # the RunConfig.dataset value, e.g. "nyu2"
    label: str  # for prose, e.g. "NYU Depth V2"
    version: str  # stored in experiment provenance
    classes: int  # output classes (1 for regression)
    input_size: tuple[int, int]  # height, width used for training crops


@dataclass(frozen=True)
class MetricSpec:
    name: str  # key in experiment outputs, e.g. "abs_rel"
    label: str  # for prose and tables, e.g. "AbsRel"
    higher_is_better: bool
    start: tuple[float, float]  # range of the value after the first epoch
    final: tuple[float, float]  # range of the converged value
    floor: float  # noisy values are clamped to [floor, ceiling]
    ceiling: float


@dataclass(frozen=True)
class ProposalSpec:
    name: str
    rationale: str
    benefit: str  # may contain {dataset} and {metric}
    risk: str


@dataclass(frozen=True)
class Profile:
    key: str  # "depth" | "segmentation" | "classification"
    task: str
    application: str
    datasets: tuple[DatasetSpec, ...]  # the first one is the default
    metrics: tuple[MetricSpec, ...]  # ordered by importance; experiments use the first 2-3
    techniques: tuple[str, ...]  # title-cased technique names for paper titles
    properties: tuple[str, ...]  # title-cased adjectives for paper titles
    challenges: tuple[str, ...]
    components: tuple[str, ...]
    details: tuple[str, ...]  # one-sentence method details for abstracts
    backbones: tuple[str, ...]
    limitations: tuple[str, ...]
    gaps: tuple[str, ...]
    proposals: tuple[ProposalSpec, ...]
    name_stems: tuple[str, ...]  # for coined model names such as "DepthFormer"
    keywords: tuple[str, ...]  # topic words that select this profile
    other_tasks: tuple[str, ...]  # what off-topic search hits are about
    loss_label: str
    loss_formula: str  # LaTeX, without delimiters
    loss_symbols: str  # plain-text explanation of the formula's symbols
    model_class: str
    loss_class: str
    architecture: str  # how the README and the draft describe the network


DEPTH = Profile(
    key="depth",
    task="monocular depth estimation",
    application="robot navigation, augmented reality and 3D scene understanding",
    datasets=(
        DatasetSpec("nyu2", "NYU Depth V2", "2025.03", 1, (480, 640)),
        DatasetSpec("kitti", "KITTI", "eigen-2014", 1, (352, 1216)),
        DatasetSpec("diode", "DIODE", "1.1", 1, (768, 1024)),
        DatasetSpec("scannet", "ScanNet", "v2", 1, (480, 640)),
        DatasetSpec("sunrgbd", "SUN RGB-D", "2015.1", 1, (480, 640)),
    ),
    metrics=(
        MetricSpec("abs_rel", "AbsRel", False, (0.38, 0.52), (0.118, 0.158), 0.01, 2.0),
        MetricSpec("rmse", "RMSE", False, (1.35, 1.85), (0.43, 0.58), 0.05, 5.0),
        MetricSpec("delta1", "δ1", True, (0.30, 0.45), (0.80, 0.885), 0.0, 0.999),
        MetricSpec("log10", "log10 error", False, (0.17, 0.24), (0.049, 0.066), 0.005, 1.0),
    ),
    techniques=(
        "Vision Transformers",
        "Diffusion Priors",
        "Self-Supervised Learning",
        "Knowledge Distillation",
        "Multi-Scale Feature Fusion",
        "Uncertainty Estimation",
        "Foundation Models",
        "State Space Models",
        "Contrastive Pretraining",
        "Geometric Priors",
        "Synthetic Data",
        "Test-Time Adaptation",
    ),
    properties=(
        "Robust",
        "Efficient",
        "Scale-Aware",
        "Uncertainty-Aware",
        "Zero-Shot",
        "Lightweight",
        "Generalizable",
        "Edge-Preserving",
    ),
    challenges=(
        "scale ambiguity",
        "reflective and textureless surfaces",
        "the gap between synthetic and real indoor scenes",
        "thin structures and depth discontinuities",
        "low-light images",
        "unseen camera intrinsics",
    ),
    components=(
        "a multi-scale decoder",
        "a scale-invariant objective",
        "an edge-aware refinement head",
        "a lightweight uncertainty branch",
        "a surface-normal auxiliary head",
        "a learned global scale token",
    ),
    details=(
        "An auxiliary surface-normal head regularizes the predicted geometry.",
        "The decoder fuses features from four scales before a final refinement step.",
        "Training mixes labeled indoor scenes with pseudo-labeled video frames.",
        "A learned global scale token recovers metric depth from relative predictions.",
        "Predictions are refined by an edge-aware upsampling module.",
        "Per-pixel variance estimates down-weight unreliable supervision.",
    ),
    backbones=("ResNet-50", "ConvNeXt-T", "ViT-S/14", "Swin-T", "EfficientNet-B3", "MobileNetV3-L"),
    limitations=(
        "Evaluated only on indoor scenes; outdoor generalization is untested.",
        "Needs a large teacher network at training time.",
        "Inference speed on embedded hardware is not reported.",
        "Predicts relative depth; metric scale needs per-dataset fine-tuning.",
        "Ablations use a single random seed.",
        "Errors grow sharply for surfaces farther than 8 m.",
        "Assumes known camera intrinsics at test time.",
    ),
    gaps=(
        "Metric scale without per-dataset fine-tuning",
        "Robustness on reflective and transparent surfaces",
        "Real-time inference on consumer GPUs with 6 GB of memory",
        "Calibrated uncertainty for downstream planning",
        "Sharp depth discontinuities at object boundaries",
        "Reproducible comparisons: most papers report single-seed results",
    ),
    proposals=(
        ProposalSpec(
            "Scale-aware distillation from a frozen foundation teacher",
            "Depth foundation models generalize well but are too heavy for the lab's GPU. "
            "Distilling their relative depth plus a learned global scale into a small student "
            "keeps most of the accuracy at a fraction of the cost.",
            "Lower {metric} on {dataset} than a student trained from scratch, with fewer than "
            "15M parameters.",
            "Teacher errors on reflective surfaces transfer to the student.",
        ),
        ProposalSpec(
            "Edge-preserving multi-scale decoder with SILog and gradient losses",
            "Several included papers attribute their gains at object boundaries to multi-scale "
            "fusion and gradient-matching terms, both cheap to add to a compact encoder-decoder.",
            "Sharper depth discontinuities and a better {metric} on {dataset}.",
            "Gradient terms can amplify sensor noise around invalid pixels.",
        ),
        ProposalSpec(
            "Uncertainty-weighted self-training on unlabeled frames",
            "Pseudo-labels filtered by predicted variance let the model learn from raw video "
            "frames without extra annotation.",
            "Better robustness on scenes that are rare in the labeled {dataset} split.",
            "Confirmation bias if the uncertainty estimate is poorly calibrated.",
        ),
        ProposalSpec(
            "Lightweight state-space encoder for long-range context",
            "Recent work suggests state-space blocks capture global scene layout at a lower "
            "memory cost than attention, which matters on a 6 GB GPU.",
            "Global context within the memory budget and a lower {metric} on {dataset}.",
            "Few reference implementations exist, and training may be unstable.",
        ),
    ),
    name_stems=("Depth", "Geo", "Metric", "Scale", "Dense", "Focal", "Vista", "Pano"),
    keywords=("depth", "stereo", "disparity", "monocular", "lidar", "point cloud", "nyu"),
    other_tasks=(
        "optical flow estimation",
        "visual odometry",
        "image deblurring",
        "6-DoF object pose estimation",
    ),
    loss_label="scale-invariant logarithmic (SILog) loss",
    loss_formula=(
        r"\mathcal{L}_{silog} = \sqrt{\frac{1}{n}\sum_{i} g_i^{2} - "
        r"\frac{\lambda}{n^{2}}\Big(\sum_{i} g_i\Big)^{2}}, \qquad "
        r"g_i = \log \hat{d}_i - \log d_i"
    ),
    loss_symbols=(
        "where g_i is the log-depth error at valid pixel i, n is the number of valid pixels, and "
        "λ weighs the mean error against the variance, so a global scale error is penalized "
        "less than structural errors."
    ),
    model_class="DepthNet",
    loss_class="DepthLoss",
    architecture="U-Net-style encoder-decoder",
)

SEGMENTATION = Profile(
    key="segmentation",
    task="semantic segmentation",
    application="autonomous driving and robot perception",
    datasets=(
        DatasetSpec("cityscapes", "Cityscapes", "fine-2016", 19, (512, 1024)),
        DatasetSpec("ade20k", "ADE20K", "2016.1", 150, (512, 512)),
        DatasetSpec("voc2012", "PASCAL VOC 2012", "aug-2012", 21, (512, 512)),
        DatasetSpec("cocostuff", "COCO-Stuff", "164k", 171, (512, 512)),
        DatasetSpec("camvid", "CamVid", "2008.1", 11, (360, 480)),
    ),
    metrics=(
        MetricSpec("miou", "mIoU", True, (0.08, 0.16), (0.58, 0.72), 0.0, 0.99),
        MetricSpec("pixel_acc", "pixel accuracy", True, (0.45, 0.62), (0.89, 0.94), 0.0, 0.999),
        MetricSpec("boundary_f1", "boundary F1", True, (0.18, 0.30), (0.60, 0.71), 0.0, 0.99),
    ),
    techniques=(
        "Vision Transformers",
        "Mask Classification",
        "Self-Training",
        "Knowledge Distillation",
        "Contrastive Learning",
        "Foundation Models",
        "Domain Adaptation",
        "Boundary Refinement",
        "Multi-Scale Context",
        "Open-Vocabulary Learning",
    ),
    properties=(
        "Robust",
        "Efficient",
        "Real-Time",
        "Label-Efficient",
        "Boundary-Aware",
        "Domain-Generalizable",
        "Lightweight",
    ),
    challenges=(
        "thin and rare classes",
        "imprecise object boundaries",
        "domain shift between cities",
        "the cost of dense annotation",
        "night-time and adverse weather",
    ),
    components=(
        "a pyramid pooling module",
        "a boundary refinement head",
        "class-balanced sampling",
        "a lightweight attention decoder",
        "an auxiliary edge loss",
    ),
    details=(
        "A pyramid pooling module aggregates context at four scales.",
        "Class-balanced sampling raises the frequency of rare categories during training.",
        "A boundary head predicts edges that sharpen the final masks.",
        "Pseudo-labels from a larger teacher supervise unlabeled images.",
        "The decoder upsamples with learned offsets instead of bilinear interpolation.",
    ),
    backbones=("ResNet-101", "MiT-B2", "ConvNeXt-S", "Swin-B", "MobileNetV3-L"),
    limitations=(
        "Reports results on a single dataset only.",
        "Rare classes still fall below 30% IoU.",
        "Requires a large teacher model for pseudo-labels.",
        "Inference speed is measured on a data-centre GPU only.",
        "Ablations are run with one random seed.",
    ),
    gaps=(
        "Accuracy on thin and rare classes",
        "Generalization from one city or domain to another",
        "Boundary quality at real-time inference speed",
        "Training with a fraction of the dense labels",
        "Reproducible comparisons across crop sizes and schedules",
    ),
    proposals=(
        ProposalSpec(
            "Boundary-aware lightweight decoder with a Dice term",
            "Included papers attribute most boundary errors to coarse upsampling, which a "
            "light decoder with an auxiliary Dice term addresses at little extra cost.",
            "Higher {metric} on {dataset}, especially on thin classes.",
            "The Dice term can be unstable for classes absent from a batch.",
        ),
        ProposalSpec(
            "Class-balanced self-training with confidence thresholds",
            "Pseudo-labels with per-class thresholds reduce the bias toward frequent classes.",
            "Better rare-class accuracy and a higher {metric} on {dataset}.",
            "Wrong pseudo-labels reinforce themselves without careful thresholds.",
        ),
        ProposalSpec(
            "Distillation from a frozen segmentation foundation model",
            "Large models give strong masks but cannot train on a 6 GB GPU; a small student can "
            "learn from their predictions.",
            "Most of the teacher's {metric} on {dataset} at a fraction of the compute.",
            "The teacher's label space may not match the dataset's classes.",
        ),
        ProposalSpec(
            "Multi-scale context module with efficient attention",
            "Global context helps large stuff classes, and linear attention keeps memory low.",
            "A higher {metric} on {dataset} for large regions.",
            "Attention adds latency at high resolution.",
        ),
    ),
    name_stems=("Seg", "Mask", "Scene", "Pixel", "City", "Region"),
    keywords=("segment", "parsing", "panoptic", "mask"),
    other_tasks=("object tracking", "image captioning", "depth completion", "super-resolution"),
    loss_label="cross-entropy with a Dice term",
    loss_formula=(
        r"\mathcal{L}_{seg} = -\frac{1}{N}\sum_{i}\log p_{i,y_i} + "
        r"\lambda\Big(1 - \frac{2\sum_{i} p_{i} y_{i}}{\sum_{i} p_{i} + \sum_{i} y_{i}}\Big)"
    ),
    loss_symbols=(
        "where p_{i,y_i} is the predicted probability of the true class at pixel i, N is the "
        "number of labeled pixels, and λ weighs the Dice overlap term that favours rare "
        "classes and sharp boundaries."
    ),
    model_class="SegNetLite",
    loss_class="SegmentationLoss",
    architecture="U-Net-style encoder-decoder",
)

CLASSIFICATION = Profile(
    key="classification",
    task="image classification",
    application="visual recognition in deployed systems",
    datasets=(
        DatasetSpec("cifar100", "CIFAR-100", "1.0", 100, (32, 32)),
        DatasetSpec("cifar10", "CIFAR-10", "1.0", 10, (32, 32)),
        DatasetSpec("imagenet1k", "ImageNet-1k", "2012", 1000, (224, 224)),
        DatasetSpec("tinyimagenet", "Tiny ImageNet", "2015", 200, (64, 64)),
    ),
    metrics=(
        MetricSpec("top1", "top-1 accuracy", True, (0.06, 0.14), (0.68, 0.79), 0.0, 0.999),
        MetricSpec("top5", "top-5 accuracy", True, (0.18, 0.32), (0.89, 0.955), 0.0, 0.999),
        MetricSpec("ece", "ECE", False, (0.14, 0.24), (0.028, 0.06), 0.001, 1.0),
    ),
    techniques=(
        "Vision Transformers",
        "Self-Supervised Pretraining",
        "Knowledge Distillation",
        "Data Augmentation",
        "Mixture of Experts",
        "Contrastive Learning",
        "Label Smoothing",
        "Long-Tailed Learning",
        "Test-Time Adaptation",
    ),
    properties=(
        "Robust",
        "Efficient",
        "Calibrated",
        "Data-Efficient",
        "Lightweight",
        "Shift-Resilient",
    ),
    challenges=(
        "long-tailed label distributions",
        "distribution shift at test time",
        "overconfident predictions",
        "limited labeled data",
        "spurious correlations",
    ),
    components=(
        "a token-mixing block",
        "a calibration-aware loss",
        "strong data augmentation",
        "a distillation token",
        "a re-balanced classifier head",
    ),
    details=(
        "Strong augmentation with mixed samples regularizes the classifier.",
        "A distillation token learns from a larger convolutional teacher.",
        "The classifier head is re-balanced after representation learning.",
        "Temperature scaling on a held-out split calibrates the confidence scores.",
        "Depthwise convolutions keep the parameter count low.",
    ),
    backbones=("ResNet-18", "ResNet-50", "ViT-S/16", "ConvNeXt-T", "EfficientNet-B0"),
    limitations=(
        "Calibration is not evaluated under distribution shift.",
        "Gains shrink at larger model scales.",
        "Relies on a large teacher at training time.",
        "Results use a single random seed.",
        "Training cost is not reported.",
    ),
    gaps=(
        "Calibrated confidence under distribution shift",
        "Accuracy on rare classes in long-tailed data",
        "Strong results with small training budgets",
        "Fair comparisons: training recipes differ widely between papers",
        "Robustness to common corruptions",
    ),
    proposals=(
        ProposalSpec(
            "Compact CNN with label smoothing and strong augmentation",
            "Several included papers show that the training recipe matters as much as the "
            "architecture for small models.",
            "A higher {metric} on {dataset} within a small compute budget.",
            "Heavy augmentation can slow convergence.",
        ),
        ProposalSpec(
            "Knowledge distillation from a frozen pretrained teacher",
            "A small student learns soft targets from a large pretrained model, which improves "
            "both accuracy and calibration.",
            "A better {metric} on {dataset} than training from labels alone.",
            "The teacher's biases transfer to the student.",
        ),
        ProposalSpec(
            "Re-balanced classifier head for long-tailed data",
            "Decoupling representation learning from classifier balancing helps rare classes.",
            "Improved rare-class accuracy and {metric} on {dataset}.",
            "Gains depend on the class distribution of the split.",
        ),
        ProposalSpec(
            "Calibration-aware training with temperature scaling",
            "Overconfidence is a recurring limitation in the included papers.",
            "A lower ECE and a stable {metric} on {dataset}.",
            "Calibration may degrade under distribution shift.",
        ),
    ),
    name_stems=("Vision", "Mix", "Tiny", "Flex", "Calib", "Sparse"),
    keywords=("classif", "recognition", "imagenet", "cifar", "few-shot", "long-tail"),
    other_tasks=("object detection", "image retrieval", "video captioning", "style transfer"),
    loss_label="label-smoothed cross-entropy",
    loss_formula=(
        r"\mathcal{L}_{ls} = -\sum_{k=1}^{K}\Big((1-\varepsilon)\,y_k + "
        r"\frac{\varepsilon}{K}\Big)\log p_k"
    ),
    loss_symbols=(
        "where y_k is the one-hot label, p_k the predicted probability of class k among K "
        "classes, and ε the smoothing factor that limits overconfident predictions."
    ),
    model_class="CompactCNN",
    loss_class="SmoothedCrossEntropy",
    architecture="convolutional network with a global-pooling head",
)

PROFILES: tuple[Profile, ...] = (DEPTH, SEGMENTATION, CLASSIFICATION)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def profile_for(topic: str, dataset: str | None) -> Profile:
    """The domain to imitate: the dataset's if it is known, else the topic's, else depth."""
    if dataset:
        key = _key(dataset)
        for profile in PROFILES:
            if any(_key(spec.id) == key or _key(spec.label) == key for spec in profile.datasets):
                return profile
    lowered = topic.lower()
    for profile in PROFILES:
        if any(word in lowered for word in profile.keywords):
            return profile
    return DEPTH


def dataset_spec(profile: Profile, dataset: str | None) -> DatasetSpec:
    """The spec of ``dataset`` (the profile default when None; a generic one when unknown)."""
    if not dataset:
        return profile.datasets[0]
    key = _key(dataset)
    for spec in profile.datasets:
        if _key(spec.id) == key or _key(spec.label) == key:
            return spec
    default = profile.datasets[0]
    return DatasetSpec(dataset, dataset, "1.0", default.classes, default.input_size)


def metric_spec(profile: Profile, name: str) -> MetricSpec | None:
    for spec in profile.metrics:
        if spec.name == name:
            return spec
    return None
