"""Demo writing stage: a 900-1500 word Markdown draft built from the earlier stage outputs.

Every [n] marker cites an included paper from the literature stage, the results table repeats
the experiment's final metrics, and the Method section holds one LaTeX formula. Text taken from
earlier outputs is escaped (reviewers may have edited it), so the draft never contains raw HTML.
"""

import random
import re
from collections.abc import Callable

from agentic_core.demo._coding import GPU_NAME
from agentic_core.demo._people import short_author_list
from agentic_core.demo._profiles import Profile, dataset_spec, metric_spec, profile_for
from agentic_core.demo._text import (
    lower_phrase,
    markdown_text,
    revision_note,
    rng_for,
    sentence,
    subject_phrase,
    title_case,
)
from agentic_core.schemas import (
    Citation,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    PaperAnalysis,
    PaperRef,
    WritingOutput,
    WritingSection,
)

MAX_CITATIONS = 8
MIN_WORDS, TARGET_WORDS, MAX_WORDS = 900, 980, 1500
_PREPOSITIONS = re.compile(r"\b(?:for|with|via|from|on|in|under|of)\b", re.IGNORECASE)
_OPTIMIZERS = {"adamw": "AdamW", "adam": "Adam", "sgd": "SGD"}
_SUPPORTED_BY = re.compile(r"\s*Supported by [^.]*\.$")  # the method stage's evidence count
_SECTION_OBJECTIVES = (
    ("Abstract", "Summarize the problem, the method and the main result in one paragraph."),
    ("Introduction", "Motivate the problem, state the gap and list the contributions."),
    ("Related Work", "Position the work against the papers kept by the literature stage."),
    ("Method", "Describe the model and the training objective."),
    ("Experiments", "Report the setup, the provenance and the final metrics."),
    ("Discussion", "Interpret the results and state the limitations honestly."),
    ("Conclusion", "Summarize the findings and the next steps."),
    ("References", "List every cited paper with its venue and year."),
)


def writing(
    topic: str,
    literature: LiteratureOutput,
    method: MethodOutput,
    experiment: ExperimentOutput,
    seed: int,
    feedback: str = "",
) -> WritingOutput:
    """A paper draft for the recommended method and its experiment, citing included papers."""
    rng = rng_for(seed, "writing")
    dataset_id = experiment.provenance.dataset
    profile = profile_for(topic, dataset_id)
    draft = _Draft(rng, profile, topic, literature, method, experiment)
    sections = draft.sections()
    extras = draft.optional_paragraphs()
    note = revision_note(feedback)
    markdown = _render(draft.title, note, sections)
    while _words(markdown) < TARGET_WORDS and extras:
        sections["Discussion"].append(extras.pop(0))
        markdown = _render(draft.title, note, sections)
    while _words(markdown) > MAX_WORDS and len(sections["Discussion"]) > 1:
        sections["Discussion"].pop()
        markdown = _render(draft.title, note, sections)
    focus = (
        "Check that every [n] citation supports its claim and that the results table matches "
        "the experiment's final metrics."
    )
    return WritingOutput(
        title=draft.title,
        abstract=draft.abstract(plain=True),
        markdown=markdown,
        sections=[
            WritingSection(name=name, objective=objective)
            for name, objective in _SECTION_OBJECTIVES
        ],
        citations=[
            Citation(key=key, paper_id=paper.paper_id) for key, paper in draft.cited.items()
        ],
        output_format="Markdown draft with the structure of an IEEE conference paper",
        review_focus=f"{note} {focus}" if note else focus,
    )


def _words(markdown: str) -> int:
    return len(markdown.split())


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _render(title: str, note: str, sections: dict[str, list[str]]) -> str:
    parts = [f"# {markdown_text(title)}"]
    if note:
        parts.append(f"> {markdown_text(note)}")
    for name, _ in _SECTION_OBJECTIVES:
        number = _NUMBERED.get(name)
        parts.append(f"## {number}. {name}" if number else f"## {name}")
        parts.extend(sections[name])
    return "\n\n".join(parts) + "\n"


_NUMBERED = {
    "Introduction": 1,
    "Related Work": 2,
    "Method": 3,
    "Experiments": 4,
    "Discussion": 5,
    "Conclusion": 6,
}


class _Draft:
    """The pieces of the draft; text from earlier stage outputs goes through ``self.md``."""

    def __init__(
        self,
        rng: random.Random,
        profile: Profile,
        topic: str,
        literature: LiteratureOutput,
        method: MethodOutput,
        experiment: ExperimentOutput,
    ) -> None:
        self.rng = rng
        self.profile = profile
        self.literature = literature
        self.method = method
        self.experiment = experiment
        self.md: Callable[[str], str] = markdown_text
        subject = subject_phrase(topic)
        self.subject = lower_phrase(subject)
        self.dataset = dataset_spec(profile, experiment.provenance.dataset)
        self.model = str(experiment.config.get("model") or profile.model_class)
        self.recommended = next(
            (p for p in method.proposals if p.name == method.recommended_option),
            method.proposals[0],
        )
        recommended = title_case(method.recommended_option)
        if _PREPOSITIONS.search(subject):
            self.title = f"{title_case(subject)}: {recommended}"
        else:
            self.title = f"{recommended} for {title_case(subject)}"
        self.analyses: dict[str, PaperAnalysis] = {a.paper_id: a for a in literature.analyses}
        papers = [p for p in literature.papers if p.decision == "include"]
        papers.sort(key=lambda paper: paper.relevance, reverse=True)
        self.cited: dict[int, PaperRef] = dict(enumerate(papers[:MAX_CITATIONS], 1))
        self.metrics = [
            series for series in experiment.series if series.name != "loss" and series.points
        ]
        self.techniques = rng.sample(profile.techniques, 3)
        self.gap = method.research_gaps[0] if method.research_gaps else profile.gaps[0]

    # --- helpers ----------------------------------------------------------------------------

    def cite(self, *keys: int) -> str:
        known = [f"[{key}]" for key in keys if key in self.cited]
        return f" {', '.join(known)}" if known else ""

    def label(self, name: str) -> str:
        spec = metric_spec(self.profile, name)
        return spec.label if spec else self.md(name)

    def final(self, name: str) -> str:
        value = self.experiment.final_metrics.get(name)
        return "n/a" if value is None else f"{value:.3f}"

    def setting(self, key: str, default: str) -> str:
        value = self.experiment.config.get(key)
        return self.md(str(value)) if value is not None else default

    def short(self, paper: PaperRef) -> str:
        family = [author.split()[-1] for author in paper.authors]
        if len(family) == 1:
            return self.md(family[0])
        if len(family) == 2:
            return self.md(f"{family[0]} and {family[1]}")
        return self.md(f"{family[0]} et al.")

    # --- sections ---------------------------------------------------------------------------

    def abstract(self, *, plain: bool = False) -> str:
        quote = (lambda text: text) if plain else self.md
        primary = self.metrics[0].name if self.metrics else "val_loss"
        secondary = self.metrics[1].name if len(self.metrics) > 1 else "val_loss"
        epochs = self.experiment.config.get("epochs", len(self.experiment.series[0].points))
        return (
            f"{sentence(self.subject)} underpins {self.profile.application}, yet published "
            "systems are hard to reproduce on modest hardware. Building on "
            f"{len(self.cited)} papers kept by a structured literature review, we study "
            f"{quote(lower_phrase(self.method.recommended_option))}. The model, "
            f"{quote(self.model)}, is a compact {self.profile.architecture} trained with "
            f"{self.profile.loss_label} on {quote(self.dataset.label)}. In a {epochs}-epoch run "
            f"on a single {GPU_NAME}, it reaches {self.label(primary)} {self.final(primary)} and "
            f"{self.label(secondary)} {self.final(secondary)} on the validation split. We "
            "describe the method, the training protocol and its provenance record, and discuss "
            f"{quote(_lower_first(self.gap))} as the main open problem. All numbers come from "
            "one seeded run and need repeated seeds before any claim is final."
        )

    def sections(self) -> dict[str, list[str]]:
        return {
            "Abstract": [self.abstract()],
            "Introduction": self.introduction(),
            "Related Work": self.related_work(),
            "Method": self.method_section(),
            "Experiments": self.experiments(),
            "Discussion": self.discussion(),
            "Conclusion": [self.conclusion()],
            "References": [self.references()],
        }

    def introduction(self) -> list[str]:
        technique = lower_phrase(self.techniques[0])
        motivation = (
            f"{sentence(self.subject)} has advanced quickly. Recent models produce convincing "
            f"predictions on standard benchmarks{self.cite(1)}, and {technique} has become a "
            f"common ingredient{self.cite(2)}. Yet most published systems assume training "
            "budgets far beyond a single consumer GPU, and their reported gains are hard to "
            "compare because papers differ in splits, input resolution and evaluation "
            f"protocol{self.cite(3)}. A small lab therefore cannot tell which ideas will "
            "survive its own constraints."
        )
        goal = (
            "This draft follows the recommendation of the method stage, "
            f"{self.md(lower_phrase(self.method.recommended_option))}. The goal is a model "
            f"that one {GPU_NAME} can train in about an hour while staying competitive on "
            f"{self.md(self.dataset.label)}. Our contributions are:"
        )
        bullets = "\n".join(
            [
                f"- {self.md(self.model)}, a compact {self.profile.architecture} trained with "
                f"{self.profile.loss_label}, generated and unit-tested in a sandbox.",
                f"- A seeded training run on {self.md(self.dataset.label)} with a complete "
                "provenance record: image digest, code and config hashes, dataset version.",
                f"- An analysis of the remaining gap, {self.md(_lower_first(self.gap))}, grounded "
                f"in the {len(self.literature.papers)} screened papers.",
            ]
        )
        return [motivation, goal, bullets]

    def related_work(self) -> list[str]:
        keys = list(self.cited)
        if not keys:
            return [
                "The literature stage kept no papers for full reading, so this section is "
                "limited to the motivation above."
            ]
        groups = [keys[index::3] for index in range(3)]
        themes = (
            f"**{self.md(self.techniques[0])}.** Work on {self.subject} increasingly builds on "
            f"{lower_phrase(self.techniques[0])}.",
            "**Evaluation and robustness.** Several studies question how well reported gains "
            "transfer beyond a single benchmark.",
            "**Efficiency.** A smaller line of work targets models that train and run on modest "
            "hardware.",
        )
        closings = (
            "Our model borrows this idea but keeps the network small.",
            "We follow their advice and report every metric with its provenance.",
            "Our setting, one 6 GB GPU, is closest to this line of work.",
        )
        paragraphs = []
        for theme, closing, group in zip(themes, closings, groups, strict=True):
            if not group:
                continue
            sentences = [theme, *(self.paper_sentence(key) for key in group), closing]
            paragraphs.append(" ".join(sentences))
        return paragraphs

    def paper_sentence(self, key: int) -> str:
        paper = self.cited[key]
        analysis = self.analyses.get(paper.paper_id)
        plural = len(paper.authors) > 1  # "Park et al. report", "Park reports"
        who = f"{self.short(paper)} [{key}]"
        if analysis is None:
            return f"{who} {'study' if plural else 'studies'} {self.md(paper.title)}."
        if key % 2:
            text = analysis.results.rstrip(".")
            match = re.match(r"reports?\s+", text, re.IGNORECASE)
            rest = text[match.end() :] if match else _lower_first(text)
            return f"{who} {'report' if plural else 'reports'} {self.md(rest)}."
        text = _lower_first(analysis.method.rstrip("."))
        return f"{who} {'use' if plural else 'uses'} {self.md(text)}."

    def method_section(self) -> list[str]:
        proposal = self.recommended
        optimizer = self.setting("optimizer", "adamw")
        optimizer = _OPTIMIZERS.get(optimizer.lower(), optimizer)
        epochs = self.setting("epochs", "20")
        batch = self.setting("batch_size", "8")
        rationale = _SUPPORTED_BY.sub("", proposal.rationale)
        overview = (
            f"{self.md(self.model)} implements {self.md(lower_phrase(proposal.name))}. It is a "
            f"{self.profile.architecture} trained with {optimizer} for {epochs} epochs at batch "
            f"size {batch}. The sandbox harness supplies the {self.md(self.dataset.label)} "
            "loader and computes every metric, so the generated code contains only the model "
            f"and the loss. {self.md(rationale)}"
        )
        # The symbols sentence continues the one the formula ends ("..., where g_i is ...").
        objective = (
            f"We minimize the {self.profile.loss_label}:\n\n$$\n{self.profile.loss_formula}\n$$"
            f"\n\n{self.profile.loss_symbols}"
        )
        benefit = proposal.expected_benefit.rstrip(".")
        risk = proposal.risk.rstrip(".")
        expectations = (
            f"The method stage expects {self.md(_lower_first(benefit))}. The main risk it "
            f"names is that {self.md(_lower_first(risk))}."
        )
        return [overview, objective, expectations]

    def experiments(self) -> list[str]:
        provenance = self.experiment.provenance
        minutes = provenance.gpu_seconds / 60
        setup = (
            "### 4.1 Setup\n\n"
            f"We train on {self.md(self.dataset.label)} (version "
            f"{self.md(provenance.dataset_version)}) and evaluate on its validation split. "
            f"Training uses a learning rate of {self.setting('learning_rate', '0.0003')} with "
            f"{self.setting('scheduler', 'cosine')} decay, mixed precision and seed "
            f"{provenance.seed}. The run took {minutes:.0f} GPU-minutes on a single "
            f"{self.md(provenance.gpu_name or GPU_NAME)}. Its provenance pins the sandbox image "
            f"({provenance.image_digest[:19]}), the code ({provenance.code_sha256[:12]}) and the "
            f"config ({provenance.config_sha256[:12]}), so the run can be repeated exactly."
        )
        rows = ["| Metric | Split | Final value | Better |", "| --- | --- | ---: | --- |"]
        for series in self.metrics:
            better = "higher" if series.higher_is_better else "lower"
            rows.append(
                f"| {self.label(series.name)} | {series.split} | {self.final(series.name)} | "
                f"{better} |"
            )
        rows.append(f"| Loss | train | {self.final('train_loss')} | lower |")
        rows.append(f"| Loss | val | {self.final('val_loss')} | lower |")
        val_loss = next(
            (s for s in self.experiment.series if s.name == "loss" and s.split == "val"), None
        )
        points = [p for p in val_loss.points if p.value is not None] if val_loss else []
        best = min(points, key=lambda p: p.value or 0.0) if points else None
        trend = self.metric_trend()
        results = (
            "### 4.2 Results\n\n"
            "Table 1 lists the metrics after the last epoch.\n\n"
            + "\n".join(rows)
            + "\n\n"
            + trend
            + (
                f" The best validation loss ({best.value:.4f}) occurs at epoch {best.epoch}."
                if best and best.value is not None
                else ""
            )
            + self.missing_note()
        )
        return [setup, results]

    def metric_trend(self) -> str:
        parts = []
        for series in self.metrics[:2]:
            values = [p.value for p in series.points if p.value is not None]
            if len(values) >= 2:
                label = self.label(series.name)
                parts.append(f"{label} went from {values[0]:.3f} to {values[-1]:.3f}")
        if not parts:
            return "The validation metrics were not measured."
        return f"Over training, validation {' and '.join(parts)}."

    def missing_note(self) -> str:
        for series in self.metrics:
            for point in series.points:
                if point.value is None:
                    return (
                        f" The {self.label(series.name)} value at epoch {point.epoch} was not "
                        "measured and is reported as missing rather than zero."
                    )
        return ""

    def discussion(self) -> list[str]:
        primary = self.metrics[0].name if self.metrics else "val_loss"
        strongest = self.cite(*list(self.cited)[:2])
        interpretation = (
            "The results support the method stage's choice: a compact "
            f"{self.profile.architecture} reaches {self.label(primary)} {self.final(primary)} "
            f"on {self.md(self.dataset.label)} within a small compute budget. This is still "
            f"behind the strongest included papers{strongest}, which use larger backbones and "
            "longer schedules, but the gap is small enough to make the approach practical."
        )
        limitations = (
            "Two limitations stand out. First, every number comes from a single seeded run, so "
            "differences of a few percent are within run-to-run noise. Second, the gap the "
            f"method stage named first, {self.md(_lower_first(self.gap))}, remains open."
        )
        return [interpretation, limitations]

    def optional_paragraphs(self) -> list[str]:
        """Added to the Discussion, in order, while the draft is shorter than the target."""
        others = self.method.research_gaps[1:2]
        future = f", starting with {self.md(_lower_first(others[0]))}" if others else ""
        return [
            "**Threats to validity.** The validation split doubles as the test set here, and "
            "the hyperparameters come from the method stage rather than a search. A held-out "
            "split and a small sweep over the learning rate would make the comparison fairer.",
            "**Compute budget.** The whole study, including the smoke test and the training "
            f"run, fits in about {self.experiment.provenance.gpu_seconds / 3600 + 0.2:.1f} "
            "GPU-hours. This makes it realistic to repeat the run with three to five seeds and "
            "report the spread instead of a single value.",
            "**Reproducibility.** The provenance record stores the hashes of the code and the "
            "config together with the dataset version, so a reviewer can rerun exactly this "
            "experiment. Missing measurements are stored as null rather than zero, so the "
            "curves never hide a failed evaluation.",
            "**Future work.** Beyond repeated seeds, the next experiments should test the "
            f"model on a second dataset and address the remaining gaps{future}. A comparison "
            "against a distilled version of the strongest included model would show how much "
            "accuracy the compact design gives up.",
        ]

    def conclusion(self) -> str:
        primary = self.metrics[0].name if self.metrics else "val_loss"
        epochs = self.setting("epochs", "20")
        return (
            f"We presented {self.md(self.model)}, a compact model for {self.subject} that follows "
            "the recommendation of the method stage. On "
            f"{self.md(self.dataset.label)} it reaches {self.label(primary)} "
            f"{self.final(primary)} after {epochs} epochs on one {GPU_NAME}. The next steps are "
            "repeated seeds, a held-out evaluation set, and the open problem the earlier stages "
            f"highlighted: {self.md(_lower_first(self.gap))}."
        )

    def references(self) -> str:
        if not self.cited:
            return "No papers are cited."
        lines = []
        for key, paper in self.cited.items():
            authors = self.md(short_author_list(paper.authors).rstrip("."))
            venue = self.md(paper.venue or "Preprint")
            entry = f"- [{key}] {authors}. {self.md(paper.title)}. {venue}, {paper.year}."
            if paper.arxiv_id:
                entry += f" arXiv:{self.md(paper.arxiv_id)}."
            lines.append(entry)
        return "\n".join(lines)
