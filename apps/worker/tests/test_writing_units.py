"""The writing stage's pure parts: citation markers, sections between markers, the outline."""

import json

import pytest
from llm_stages_testkit import LITERATURE, outline_answer

from agentic_core.schemas import WritingSection
from agentic_worker.llm_json import InvalidModelOutputError
from agentic_worker.writing.draft import Cited, references, writing_output
from agentic_worker.writing.outline import MAX_SECTIONS, Outline, parse_outline
from agentic_worker.writing.sections import parse_section, previous_sections


def test_markers_outside_the_list_are_removed_and_ranges_cite_every_paper() -> None:
    cited = Cited(4)
    text = cited.check("As [1] and [2\N{EN DASH}4] show, [3, 9] and [5] differ [6-7]. Also [2-1].")
    assert text == "As [1] and [2\N{EN DASH}4] show, [3] and differ. Also."
    assert (sorted(cited.used), cited.removed) == ([1, 2, 3, 4], 4)


def test_code_math_links_and_intervals_are_not_citations() -> None:
    cited = Cited(2)
    text = (
        "Values in [0, 1], see [9](https://example.org), `x[9]`, $y_{[9]}$ and\n"
        "```python\nz = w[7]\n```\n$$[8]$$"
    )
    assert cited.check(text) == text
    assert (cited.used, cited.removed) == (set(), 0)


def test_the_references_list_the_cited_papers_only() -> None:
    papers = LITERATURE.papers
    assert references(papers, [2, 1]).splitlines() == [
        "- [1] Lihe Yang, Bingyi Kang, Zilong Huang et al. Depth Anything: Unleashing the Power "
        "of Large-Scale Unlabeled Data. CVPR, 2024. arXiv:2401.10891.",
        "- [2] Shariq Farooq Bhat, Ibraheem Alhashim, Peter Wonka. AdaBins: Depth Estimation "
        "Using Adaptive Bins. CVPR, 2021. doi:10.1109/cvpr46437.2021.00400.",
    ]
    assert references(papers, []) == "No paper is cited."
    # Text from scholarly databases cannot add markup.
    paper = papers[3].model_copy(update={"title": "Graphs <b>for</b> *molecules* [1]"})
    assert "Graphs &lt;b&gt;for&lt;/b&gt; \\*molecules\\* \\[1\\]." in references([paper], [1])


def test_the_draft_is_assembled_with_numbered_sections_and_its_references() -> None:
    outline = Outline(
        title="A title [7]",
        abstract="An abstract.",
        sections=(
            WritingSection(name="Introduction", objective="Motivate."),
            WritingSection(name="Method", objective="Describe."),
        ),
        output_format="Markdown",
        review_focus="Citations.",
    )
    output, removed = writing_output(outline, ["Intro [2].", "Method [2, 3]."], LITERATURE.papers)
    assert output.title == "A title"
    assert output.markdown.split("\n\n")[:7] == [
        "# A title",
        "## Abstract",
        "An abstract.",
        "## 1. Introduction",
        "Intro [2].",
        "## 2. Method",
        "Method [2, 3].",
    ]
    assert output.markdown.split("\n\n")[7:9] == [
        "## References",
        references(LITERATURE.papers, [2, 3]),
    ]
    assert ([c.key for c in output.citations], removed) == ([2, 3], 1)


def test_a_section_is_read_between_its_last_pair_of_marker_lines() -> None:
    raw = (
        "I will write it between --- BEGIN SECTION --- and --- END SECTION --- lines.\r\n"
        "--- BEGIN SECTION ---\r\n## 2. Method\r\nWe train a model [1].\r\n--- END SECTION ---\r\n"
        "Done."
    )
    assert parse_section(raw, "Method") == "We train a model [1]."
    fenced = "--- BEGIN SECTION ---\n```markdown\n### 2.1 Setup\nText.\n```\n--- END SECTION ---"
    assert parse_section(fenced, "Method") == "### 2.1 Setup\nText."  # a subsection stays
    repeated = "--- BEGIN SECTION ---\n### Method\nText.\n--- END SECTION ---"
    assert parse_section(repeated, "Method") == "Text."
    with pytest.raises(InvalidModelOutputError, match="between the lines"):
        parse_section("## Method\nText without markers.", "Method")
    with pytest.raises(InvalidModelOutputError, match="empty"):
        parse_section("--- BEGIN SECTION ---\n## Method\n--- END SECTION ---", "Method")


def test_previous_sections_are_found_by_their_name() -> None:
    markdown = "# T\n\n## Abstract\n\nA.\n\n## 1. Introduction\n\nIntro.\n\n### 1.1 Aim\n\nAim."
    assert previous_sections(markdown) == {
        "abstract": "A.",
        "introduction": "Intro.\n\n### 1.1 Aim\n\nAim.",
    }


def test_the_outline_leaves_out_the_abstract_and_the_references() -> None:
    outline = parse_outline(outline_answer(""))
    assert outline.title == "Compact Depth Transformers for Indoor Scenes"
    assert [s.name for s in outline.sections] == ["Introduction", "Method", "Experiments"]
    assert outline.review_focus == "Check every citation. Check the numbers."

    answer = json.loads(outline_answer(""))
    answer["sections"] = [{"name": "References", "objective": "List them."}]
    with pytest.raises(InvalidModelOutputError, match="no section besides"):
        parse_outline(json.dumps(answer))
    answer["sections"] = [{"name": f"Part {n}", "objective": "Cover it."} for n in range(9)]
    with pytest.raises(InvalidModelOutputError, match=f"at most {MAX_SECTIONS}"):
        parse_outline(json.dumps(answer))
    # "3D" is part of a name, not its number.
    answer["sections"] = [{"name": "3D Reconstruction", "objective": "Cover it."}]
    assert parse_outline(json.dumps(answer)).sections[0].name == "3D Reconstruction"
