"""Demo literature stage: a search plan, screened papers, reading notes and a synthesis.

Identifiers look real but are synthetic: arXiv ids use sequence numbers from 90000 up (beyond
any real monthly count), DOIs use Crossref's 10.5555 test prefix, and OpenAlex and CORE ids
start with a 9 above the ranges in use.
"""

import random
import re
from collections.abc import Callable
from dataclasses import dataclass

from agentic_core.demo._people import author_names
from agentic_core.demo._profiles import MetricSpec, Profile, dataset_spec, profile_for
from agentic_core.demo._text import (
    article,
    counted,
    join_words,
    lower_phrase,
    revision_note,
    rng_for,
    sentence,
    subject_phrase,
    title_case,
    unique,
)
from agentic_core.schemas import (
    EvidenceQuote,
    LiteratureOutput,
    PaperAnalysis,
    PaperFinding,
    PaperRef,
    PaperSource,
    ResearchPlan,
    RunConfig,
    ScreeningDecision,
)

SOURCE_LABELS: dict[str, str] = {
    "arxiv": "arXiv",
    "semantic_scholar": "Semantic Scholar",
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "core": "CORE",
    "demo": "Demo",
}

_CONFERENCES = ("CVPR", "ICCV", "ECCV", "NeurIPS", "ICML", "ICLR", "AAAI", "WACV", "BMVC", "3DV")
_JOURNALS = ("IEEE TPAMI", "IJCV", "IEEE TIP", "IEEE RA-L", "Pattern Recognition")
_ACRONYM_NAMES = (
    "PRISM",
    "ATLAS",
    "ORCA",
    "SAGE",
    "LUMEN",
    "KITE",
    "HELIX",
    "NOVA",
    "AURA",
    "CREST",
    "FLARE",
    "TIDE",
    "EMBER",
    "QUILL",
    "MOSAIC",
    "ZENITH",
)
_NAME_SUFFIXES = ("Former", "Mamba", "Diff", "Net", "Fusion", "Lite", "Prompt", "Distill", "Flow")
# Templates where the subject may itself contain prepositions ("depth estimation for robots").
_TITLES = (
    "{name}: Rethinking {subject}",
    "Revisiting {subject}: A Large-Scale Benchmark",
    "{prop} {subject}",
    "{technique} Meets {subject}",
    "Towards {prop} {subject}",
    "Benchmarking {subject} under Distribution Shift",
    "When Does {technique} Help {subject}?",
    "{name}: {prop} {subject} at Scale",
)
# Only for subjects without prepositions, where "... for {subject} with ..." still reads well.
_PREPOSITION_TITLES = (
    "{name}: {technique} for {subject}",
    "Learning {subject} from Synthetic Data",
    "{prop} {subject} with {technique}",
    "Efficient {subject} on Edge Devices",
    "{name}: {prop} {subject} via {technique}",
)
_SURVEY_TITLES = (
    "A Survey of {subject}: Methods, Datasets and Open Problems",
    "{subject}: A Review of Recent Advances",
    "{subject} in Practice: A Survey",
)
_OFF_TOPIC_TITLES = ("{name}: {technique} for {other}", "{prop} {other} with {technique}")
_OFF_TOPIC_DETAILS = (
    "A lightweight decoder keeps inference real-time on a single GPU.",
    "Training uses a curriculum from synthetic to real images.",
    "An auxiliary consistency loss stabilizes training.",
)
_PREPOSITIONS = re.compile(r"\b(?:for|with|via|from|on|in|under|of)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Facts:
    """What one demo paper is about; its title, abstract and notes are all written from this."""

    kind: str  # method | survey | other_dataset | unclear | off_topic | no_eval | workshop
    name: str
    technique: str
    prop: str
    component: str
    challenge: str
    backbone: str
    dataset: str
    metric: MetricSpec
    value: float
    gain: float
    params: float  # millions
    fps: int
    epochs: int
    learning_rate: str
    ablation: float
    other_task: str


def _bare(component: str) -> str:
    """ "a multi-scale decoder" -> "multi-scale decoder"."""
    return re.sub(r"^(?:a|an)\s+", "", component)


def research_plan(
    topic: str, seed: int, *, config: RunConfig | None = None, feedback: str = ""
) -> ResearchPlan:
    """A plausible search plan, for demo data written without the real planning agent."""
    config = config or RunConfig()
    profile = profile_for(topic, config.dataset)
    rng = rng_for(seed, "plan")
    subject = lower_phrase(subject_phrase(topic))
    dataset = dataset_spec(profile, config.dataset).label
    first, second, third = (lower_phrase(t) for t in rng.sample(profile.techniques, 3))
    queries = unique(
        [
            subject,
            f"{subject} {first}",
            f"{second} for {profile.task}",
            f"{profile.task} {dataset} benchmark",
            f"{subject} {rng.choice(profile.challenges)}",
            f"{third} {profile.task}",
        ]
    )[: rng.randint(4, 6)]
    scope = (
        f"Learning-based {subject} methods published between {config.year_from} and "
        f"{config.year_to}, with emphasis on {first} and {second}. Hand-crafted pipelines and "
        "papers without a quantitative evaluation are out of scope."
    )
    note = revision_note(feedback)
    return ResearchPlan(
        topic=" ".join(topic.split()) or subject,
        queries=queries,
        scope=f"{scope} {note}" if note else scope,
        inclusion_criteria=[
            f"Published between {config.year_from} and {config.year_to}",
            f"Proposes or evaluates a learning-based method for {subject}",
            f"Reports quantitative results on a public benchmark such as {dataset}",
            "Peer-reviewed, or an arXiv preprint with enough detail to reproduce",
        ],
        subtopics=unique(
            [sentence(first), sentence(second), sentence(third), sentence(profile.challenges[0])]
        ),
    )


def literature(
    topic: str, plan: ResearchPlan, config: RunConfig, seed: int, feedback: str = ""
) -> LiteratureOutput:
    """About ``config.max_papers`` screened papers (at least 5) for ``topic``, sorted by
    relevance, with reading notes for the included ones, key findings and a synthesis."""
    profile = profile_for(topic, config.dataset)
    rng = rng_for(seed, "literature")
    subject = subject_phrase(topic)
    main_dataset = dataset_spec(profile, config.dataset).label
    count = max(5, config.max_papers - rng.randint(0, min(2, config.max_papers // 10)))
    decisions = _decisions(rng, count)
    used_names = {profile.model_class}  # the lab's own model must not look like a paper's
    used_ids: set[str] = set()
    used_titles: set[str] = set()
    papers: list[PaperRef] = []
    facts: dict[str, _Facts] = {}
    for decision, relevance in zip(decisions, _relevance(rng, decisions), strict=True):
        fact = _facts(rng, profile, decision, main_dataset, used_names)
        year = round(rng.triangular(config.year_from, config.year_to, config.year_to))
        source = rng.choice(config.sources)
        paper = _paper(
            rng,
            fact,
            title=_title(rng, fact, subject, used_titles),
            year=year,
            source=source,
            relevance=relevance,
            decision=decision,
            reason=_reason(rng, fact, decision, lower_phrase(subject), main_dataset),
            abstract=_abstract(rng, fact, profile, lower_phrase(subject)),
            year_to=config.year_to,
            used_ids=used_ids,
        )
        papers.append(paper)
        facts[paper.paper_id] = fact
    included = [paper for paper in papers if paper.decision == "include"]
    return LiteratureOutput(
        plan=plan,
        papers=papers,
        analyses=[_analysis(rng, p, facts[p.paper_id], profile, subject) for p in included],
        key_findings=_key_findings(rng, papers, facts, profile, lower_phrase(subject)),
        synthesis=_synthesis(
            rng, papers, facts, profile, lower_phrase(subject), main_dataset, feedback
        ),
    )


def _decisions(rng: random.Random, count: int) -> list[ScreeningDecision]:
    # At least three papers to build on, and at least one "maybe" and one "exclude" to review.
    include = max(3, round(count * rng.uniform(0.38, 0.52)))
    maybe = max(1, round(count * rng.uniform(0.18, 0.28)))
    include = min(include, count - 2)
    maybe = max(1, min(maybe, count - include - 1))
    counts: tuple[tuple[ScreeningDecision, int], ...] = (
        ("include", include),
        ("maybe", maybe),
        ("exclude", count - include - maybe),
    )
    return [decision for decision, times in counts for _ in range(times)]


def _relevance(rng: random.Random, decisions: list[ScreeningDecision]) -> list[float]:
    bands = {"include": (0.72, 0.97), "maybe": (0.5, 0.71), "exclude": (0.1, 0.49)}
    scores: list[float] = []
    for decision in ("include", "maybe", "exclude"):
        low, high = bands[decision]
        band = sorted((rng.uniform(low, high) for d in decisions if d == decision), reverse=True)
        scores.extend(round(score, 2) for score in band)
    return scores


def _model_name(rng: random.Random, profile: Profile, used: set[str]) -> str:
    while True:
        if rng.random() < 0.45:
            name = rng.choice(_ACRONYM_NAMES)
        else:
            name = rng.choice(profile.name_stems) + rng.choice(_NAME_SUFFIXES)
        if name in used:
            name = f"{name}-{rng.choice(('v2', 'XL', 'S', 'Plus'))}"
        if name not in used:
            used.add(name)
            return name


def _facts(
    rng: random.Random,
    profile: Profile,
    decision: ScreeningDecision,
    main_dataset: str,
    used_names: set[str],
) -> _Facts:
    if decision == "include":
        kind = "method"
    elif decision == "maybe":
        kind = rng.choice(("survey", "other_dataset", "unclear"))
    else:
        kind = rng.choice(("off_topic", "off_topic", "no_eval", "workshop"))
    metric = rng.choice(profile.metrics[:3])
    value = rng.uniform(*metric.final)
    # Published numbers are a little better than what the lab's small demo model reaches.
    if metric.higher_is_better:
        value = min(metric.ceiling, value + rng.uniform(0.01, 0.06))
    else:
        value *= rng.uniform(0.78, 0.95)
    others = [spec.label for spec in profile.datasets if spec.label != main_dataset]
    use_main = kind != "other_dataset" and (rng.random() < 0.65 or not others)
    large = rng.random() < 0.5  # half the papers use a large backbone
    return _Facts(
        kind=kind,
        name=_model_name(rng, profile, used_names),
        technique=rng.choice(profile.techniques),
        prop=rng.choice(profile.properties),
        component=rng.choice(profile.components),
        challenge=rng.choice(profile.challenges),
        backbone=rng.choice(profile.backbones),
        dataset=main_dataset if use_main else rng.choice(others or [main_dataset]),
        metric=metric,
        value=value,
        gain=rng.uniform(2.5, 18.0),
        params=round(rng.uniform(60.0, 340.0) if large else rng.uniform(3.5, 60.0), 1),
        fps=rng.randint(9, 140),
        epochs=rng.choice((20, 25, 30, 40, 50)),
        learning_rate=rng.choice(("1e-4", "2e-4", "3e-4", "5e-5")),
        ablation=rng.uniform(4.0, 21.0),
        other_task=rng.choice(profile.other_tasks),
    )


def _title(rng: random.Random, fact: _Facts, subject: str, used: set[str]) -> str:
    if fact.kind == "survey":
        templates = _SURVEY_TITLES
    elif fact.kind == "off_topic":
        templates = _OFF_TOPIC_TITLES
    elif _PREPOSITIONS.search(subject):
        templates = _TITLES
    else:
        templates = _TITLES + _PREPOSITION_TITLES
    values = {
        "name": fact.name,
        "subject": title_case(subject),
        "prop": fact.prop,
        "technique": fact.technique,
        "other": title_case(fact.other_task),
    }
    for _ in range(8):
        title = rng.choice(templates).format(**values)
        if title.lower() not in used:
            break
    else:  # coined names are unique, so this title is too
        title = f"{fact.name}: {fact.prop} {values['subject']}"
    used.add(title.lower())
    return title


def _abstract(rng: random.Random, fact: _Facts, profile: Profile, subject: str) -> str:
    technique = lower_phrase(fact.technique)
    if fact.kind == "survey":
        return " ".join(
            [
                f"We review {rng.randint(60, 240)} papers on {subject} and organize them by "
                f"supervision, architecture and training data.",
                f"We compare the results reported on {fact.dataset} under a common protocol and "
                f"find that differences in evaluation crops explain part of the reported gains.",
                f"We identify {fact.challenge} as the main open problem and discuss how "
                f"{technique} may address it.",
                "A public table of results accompanies the survey.",
            ]
        )
    if fact.kind == "off_topic":
        return " ".join(
            [
                f"{sentence(fact.other_task)} is a core problem in computer vision.",
                f"We propose {fact.name}, which brings {technique} to {fact.other_task}.",
                rng.choice(_OFF_TOPIC_DETAILS),
                f"{fact.name} improves over strong baselines by {fact.gain:.1f}% on standard "
                "benchmarks.",
            ]
        )
    problem = rng.choice(
        (
            f"{sentence(subject)} remains difficult because of {fact.challenge}.",
            f"Despite rapid progress, {subject} models still struggle with {fact.challenge}.",
            f"Most {subject} methods are tuned on a single benchmark, which hides their "
            f"sensitivity to {fact.challenge}.",
        )
    )
    proposal = rng.choice(
        (
            f"We propose {fact.name}, which combines {technique} with {fact.component}.",
            f"We introduce {fact.name}, {article(fact.prop)} {lower_phrase(fact.prop)} model "
            f"built on {technique} and {fact.component}.",
            f"This paper presents {fact.name}, {article(fact.backbone)} {fact.backbone}-based "
            f"network trained with {technique}.",
        )
    )
    verb = "improves" if fact.metric.higher_is_better else "reduces"
    result = rng.choice(
        (
            f"On {fact.dataset}, {fact.name} {verb} {fact.metric.label} by {fact.gain:.1f}% "
            "relative to the strongest baseline.",
            f"{fact.name} reaches {fact.metric.label} {fact.value:.3f} on {fact.dataset} while "
            f"running at {fact.fps} FPS on a single GPU.",
            f"Experiments on {fact.dataset} show a {fact.gain:.1f}% gain in {fact.metric.label} "
            f"over prior work with {fact.params:g}M parameters.",
        )
    )
    closing = rng.choice(
        (
            f"Ablations attribute most of the improvement to the {_bare(fact.component)}.",
            f"We also analyse failure cases caused by {fact.challenge}.",
            "Code and trained weights are publicly available.",
            f"The model trains on a single consumer GPU in under {rng.randint(6, 30)} hours.",
        )
    )
    sentences = [problem, proposal, rng.choice(profile.details), result, closing]
    if fact.kind == "no_eval":
        sentences[3] = "We illustrate the approach with qualitative examples."
    if fact.kind == "workshop":
        sentences = sentences[:3]
    return " ".join(sentences)


def _reason(
    rng: random.Random,
    fact: _Facts,
    decision: ScreeningDecision,
    subject: str,
    main_dataset: str,
) -> str:
    technique = lower_phrase(fact.technique)
    if decision == "include":
        return rng.choice(
            (
                f"Proposes {technique} for {subject} and reports {fact.metric.label} on "
                f"{fact.dataset}.",
                f"Directly addresses {fact.challenge}, with a reproducible evaluation on "
                f"{fact.dataset}.",
                f"Strong {fact.dataset} results ({fact.metric.label} {fact.value:.3f}) and an "
                f"ablation of the {_bare(fact.component)}.",
            )
        )
    return {
        "survey": "Survey without new experiments; useful background for related work.",
        "other_dataset": f"Relevant {technique} idea, but evaluated only on {fact.dataset}, "
        f"not on {main_dataset}.",
        "unclear": "Promising, but the training details and evaluation protocol are missing.",
        "off_topic": f"Studies {fact.other_task}, which is outside the scope of {subject}.",
        "no_eval": "No quantitative evaluation on a public benchmark.",
        "workshop": "Two-page workshop abstract without enough detail to assess the method.",
    }[fact.kind]


def _paper(
    rng: random.Random,
    fact: _Facts,
    *,
    title: str,
    year: int,
    source: PaperSource,
    relevance: float,
    decision: ScreeningDecision,
    reason: str,
    abstract: str,
    year_to: int,
    used_ids: set[str],
) -> PaperRef:
    preprint = source in ("arxiv", "semantic_scholar") and rng.random() < 0.3
    venue = "arXiv" if preprint else _venue(rng, year)
    if fact.kind == "workshop":
        venue = f"{venue} Workshops" if venue in _CONFERENCES else venue
    arxiv_id = None
    if source == "arxiv" or (year >= 2007 and rng.random() < 0.45):
        arxiv_id = _unique_id(used_ids, lambda: _arxiv_id(rng, year))
    doi = None
    if venue != "arXiv" and (source in ("crossref", "openalex") or rng.random() < 0.8):
        slug = re.sub(r"[^a-z0-9]", "", venue.lower())
        doi = _unique_id(used_ids, lambda: f"10.5555/{slug}.{year}.9{rng.randrange(10_000):04d}")
    native = {
        "semantic_scholar": f"{rng.getrandbits(160):040x}",
        "openalex": f"W9{rng.randrange(10**9):09d}",
        "core": f"9{rng.randrange(10**8):08d}",
    }.get(source, "")
    if arxiv_id:
        paper_id = f"arxiv:{arxiv_id}"
    elif doi:
        paper_id = f"doi:{doi}"
    else:
        paper_id = f"{source}:{native}"
    url = {
        "arxiv": f"https://arxiv.org/abs/{arxiv_id}",
        "semantic_scholar": f"https://www.semanticscholar.org/paper/{native}",
        "openalex": f"https://openalex.org/{native}",
        "crossref": f"https://doi.org/{doi}",
        "core": f"https://core.ac.uk/works/{native}",
    }[source]
    if source == "crossref" and doi is None:  # Crossref only indexes DOIs
        url = f"https://doi.org/10.5555/preprint.{year}.9{rng.randrange(10_000):04d}"
    # Older and more relevant papers are cited more; counts are heavy-tailed like real ones.
    age = max(0, year_to - year)
    citations = rng.lognormvariate(1.0 + 0.8 * age, 0.9) * (1.5 if decision == "include" else 1)
    return PaperRef(
        paper_id=paper_id,
        title=title,
        authors=author_names(rng, rng.randint(2, 7)),
        year=year,
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
        abstract=abstract,
        citation_count=None if rng.random() < 0.06 else min(int(citations), 9000),
        source=source,
        pdf_available=arxiv_id is not None or rng.random() < 0.55,
        relevance=relevance,
        decision=decision,
        decision_reason=reason,
    )


def _venue(rng: random.Random, year: int) -> str:
    if rng.random() < 0.25:
        return rng.choice(_JOURNALS)
    venues = [
        venue
        for venue in _CONFERENCES
        # ICCV meets in odd years and ECCV in even ones; ICLR and 3DV started in 2013.
        if not (venue == "ICCV" and year % 2 == 0)
        and not (venue == "ECCV" and year % 2 == 1)
        and not (venue in ("ICLR", "3DV") and year < 2013)
    ]
    venue = rng.choice(venues)
    return "NIPS" if venue == "NeurIPS" and year < 2018 else venue


def _arxiv_id(rng: random.Random, year: int) -> str:
    prefix = f"{year % 100:02d}{rng.randint(1, 12):02d}"
    if year >= 2015:
        return f"{prefix}.9{rng.randrange(10_000):04d}"
    if year >= 2007:
        return f"{prefix}.9{rng.randrange(1000):03d}"
    return f"cs/{prefix}9{rng.randrange(100):02d}"  # the old archive/YYMMNNN form


def _unique_id(used: set[str], make: Callable[[], str]) -> str:
    while True:
        candidate = make()
        if candidate not in used:
            used.add(candidate)
            return candidate


def _analysis(
    rng: random.Random, paper: PaperRef, fact: _Facts, profile: Profile, subject: str
) -> PaperAnalysis:
    technique = lower_phrase(fact.technique)
    direction = "better" if fact.metric.higher_is_better else "lower"
    return PaperAnalysis(
        paper_id=paper.paper_id,
        contribution=f"Introduces {fact.name}, which applies {technique} to "
        f"{lower_phrase(subject)} with {fact.component}.",
        method=f"{sentence(article(fact.backbone))} {fact.backbone} encoder with "
        f"{fact.component}, trained end to end on {fact.dataset} for {fact.epochs} epochs "
        f"(learning rate {fact.learning_rate}).",
        results=f"Reports {fact.metric.label} {fact.value:.3f} on {fact.dataset}, "
        f"{fact.gain:.1f}% {direction} than the strongest baseline.",
        limitations=rng.choice(profile.limitations),
        evidence=_evidence(rng, fact),
    )


def _evidence(rng: random.Random, fact: _Facts) -> list[EvidenceQuote]:
    candidates = [
        (
            f"On {fact.dataset}, {fact.name} achieves {fact.metric.label} of {fact.value:.3f}.",
            6,
            9,
        ),
        (
            f"Removing the {_bare(fact.component)} increases the error by {fact.ablation:.1f}% "
            f"(Table {rng.randint(2, 5)}).",
            7,
            10,
        ),
        (
            f"We train for {fact.epochs} epochs with AdamW and a peak learning rate of "
            f"{fact.learning_rate}.",
            4,
            6,
        ),
        (f"Our approach remains most fragile under {fact.challenge}.", 9, 12),
        (f"The {fact.backbone} encoder is initialized from ImageNet-pretrained weights.", 3, 5),
    ]
    chosen = rng.sample(candidates, rng.randint(1, 3))
    quotes = [EvidenceQuote(quote=text, page=rng.randint(low, high)) for text, low, high in chosen]
    return sorted(quotes, key=lambda quote: quote.page)


def _key_findings(
    rng: random.Random,
    papers: list[PaperRef],
    facts: dict[str, _Facts],
    profile: Profile,
    subject: str,
) -> list[PaperFinding]:
    usable = {"method", "survey", "other_dataset", "unclear"}
    candidates = [p for p in papers if p.decision == "include"] + [
        p for p in papers if p.decision == "maybe" and facts[p.paper_id].kind in usable
    ]
    findings = []
    for paper in candidates[: rng.randint(4, 6)]:
        fact = facts[paper.paper_id]
        technique = lower_phrase(fact.technique)
        if fact.kind == "survey":
            summary = (
                f"Survey of recent {subject} methods; names {fact.challenge} as the main open "
                "problem."
            )
        elif fact.kind == "other_dataset":
            summary = f"{fact.name} applies {technique} to {subject}, but only on {fact.dataset}."
        elif fact.kind == "unclear":
            summary = (
                f"{fact.name} reports promising {fact.metric.label} gains, but the evaluation "
                "protocol is under-specified."
            )
        else:
            effect = rng.choice(
                (
                    "gives the largest single gain",
                    f"improves robustness to {fact.challenge}",
                    "transfers to unseen scenes without fine-tuning",
                    "matches larger models at a fraction of the compute",
                )
            )
            summary = (
                f"{fact.name} shows that {technique} {effect} ({fact.metric.label} "
                f"{fact.value:.3f} on {fact.dataset})."
            )
        findings.append(
            PaperFinding(
                title=paper.title,
                source=SOURCE_LABELS[paper.source],
                summary=summary,
                url=paper.url,
                paper_id=paper.paper_id,
            )
        )
    return findings


def _synthesis(
    rng: random.Random,
    papers: list[PaperRef],
    facts: dict[str, _Facts],
    profile: Profile,
    subject: str,
    main_dataset: str,
    feedback: str,
) -> str:
    included = [paper for paper in papers if paper.decision == "include"]
    years = sorted({paper.year for paper in papers})
    span = f"in {years[0]}" if len(years) == 1 else f"between {years[0]} and {years[-1]}"
    techniques = unique(
        [lower_phrase(facts[p.paper_id].technique) for p in included]
        + [lower_phrase(t) for t in profile.techniques]
    )
    leaders = sorted(included, key=lambda p: facts[p.paper_id].gain, reverse=True)
    first, second = facts[leaders[0].paper_id], facts[leaders[1].paper_id]
    opening = (
        f"The search screened {len(papers)} papers on {subject} published {span} and kept "
        f"{len(included)} for full reading. Two lines of work dominate: {techniques[0]} and "
        f"{techniques[1]}. {first.name} and {second.name} report the largest gains: "
        f"{first.gain:.1f}% in {first.metric.label} on {first.dataset} and {second.gain:.1f}% in "
        f"{second.metric.label} on {second.dataset}."
    )
    challenge = rng.choice(profile.challenges)
    explicit = rng.randint(1, max(1, len(included) // 3))
    evaluate = counted(explicit, "evaluates", "evaluate")
    evidence = (
        f"Evidence is thinner for {challenge}: only {explicit} of the {len(included)} included "
        f"papers {evaluate} it explicitly. Reported numbers are also hard to compare, because "
        "the papers differ in splits, input resolution and evaluation protocol. The most common "
        f"limitation in the reading notes is: {rng.choice(profile.limitations)}"
    )
    metrics = join_words(metric.label for metric in profile.metrics[:3])
    direction = (
        f"For the method stage, the most promising direction is to combine {techniques[0]} with "
        f"a {_bare(rng.choice(profile.components))} in a model small enough for a 6 GB GPU, and "
        f"to evaluate it on {main_dataset} with {metrics}."
    )
    paragraphs = [opening, evidence, *([direction] if rng.random() < 0.7 else [])]
    note = revision_note(feedback)
    if note:
        paragraphs[0] = f"{note} {paragraphs[0]}"
    return "\n\n".join(paragraphs)
