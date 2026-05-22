from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agentic_ai_system.crew import AgenticAiSystem
from agentic_ai_system.orchestration.flow_utils import kickoff_with_retry, parse_model_output, run_id
from agentic_ai_system.schemas.fetches import LiteratureFetchOutput, PaperAnalysisOutput, PaperFetchResult
from agentic_ai_system.schemas.models import LiteratureResearchOutput, LiteratureScreenOutput, PaperFinding
from agentic_ai_system.storage.artifact_contract import store_stage_artifact_manifest
from agentic_ai_system.storage.literature_analysis_storage import store_literature_analysis_output
from agentic_ai_system.storage.literature_fetch_storage import store_literature_fetch_output
from agentic_ai_system.storage.literature_screen_storage import store_literature_screen_output
from agentic_ai_system.storage.literature_storage import store_literature_output
from agentic_ai_system.tools import ArxivSearchTool, PaperFullTextFetchTool, SemanticScholarSearchTool
from agentic_ai_system.ui.bridge import ui_update_queue


def build_literature_queries(topic: str) -> list[str]:
    base = topic.strip()
    queries = [base]
    lowered = base.lower()
    if "unet" in lowered or "u-net" in lowered:
        queries.extend(
            [
                "U-Net segmentation model medical imaging",
                "UNet architecture semantic segmentation",
                "Attention U-Net nnU-Net TransU-Net",
                "U-Net diffusion model denoising",
            ]
        )
    else:
        queries.extend([f"{base} survey", f"{base} recent advances", f"{base} benchmark"])
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = query.lower()
        if key not in seen:
            deduped.append(query)
            seen.add(key)
    return deduped


def paper_relevance_score(paper: dict[str, Any], topic: str) -> int:
    text = f"{paper.get('title', '')} {paper.get('summary', '')}".lower()
    topic_tokens = [token for token in re.findall(r"[a-z0-9\-]+", topic.lower()) if len(token) > 2]
    score = sum(1 for token in topic_tokens if token in text)
    boosters = ["unet", "u-net", "segmentation", "medical imaging", "attention u-net", "nnu-net", "transunet"]
    score += sum(2 for token in boosters if token in text)
    return score


def is_topic_specific_match(paper: dict[str, Any], topic: str) -> bool:
    text = f"{paper.get('title', '')} {paper.get('summary', '')}".lower()
    lowered_topic = topic.lower()
    if "unet" in lowered_topic or "u-net" in lowered_topic:
        required_markers = ["unet", "u-net", "nnunet", "transunet", "attention u-net"]
        return any(marker in text for marker in required_markers)
    return True


def collect_literature_bundle(topic: str) -> dict[str, Any]:
    queries = build_literature_queries(topic)
    aggregated: list[dict[str, Any]] = []
    source_errors: list[dict[str, str]] = []
    
    print(f"\n📚 Starting literature search for topic: '{topic}'")
    print(f"📍 Generated queries: {queries}\n")
    
    semantic_scholar_exhausted = False  # Track if rate-limited
    
    for idx, query in enumerate(queries):
        print(f"  🔍 Searching with query: '{query}'")
        
        # Always try ArXiv
        arxiv_tool = ArxivSearchTool()
        try:
            raw = arxiv_tool._run(query, max_results=8)
            payload = json.loads(raw)
            if payload.get("error"):
                error_msg = payload["error"]
                print(f"    ⚠️  {arxiv_tool.name}: {error_msg}")
                source_errors.append(
                    {
                        "source": payload.get("source", arxiv_tool.name),
                        "query": query,
                        "error": error_msg,
                    }
                )
            else:
                papers_count = len(payload.get("papers", []))
                print(f"    ✅ {arxiv_tool.name}: Found {papers_count} papers")
                
                for paper in payload.get("papers", []):
                    item = dict(paper)
                    item["query"] = query
                    if not is_topic_specific_match(item, topic):
                        print(f"       ❌ Filtered out: {item.get('title', '')[:50]}")
                        continue
                    item["relevance_score"] = paper_relevance_score(item, topic)
                    aggregated.append(item)
                    print(f"       ✅ Added (score={item['relevance_score']}): {item.get('title', '')[:50]}")
        except Exception as e:
            print(f"    ❌ {arxiv_tool.name}: Exception: {e}")
            source_errors.append({
                "source": arxiv_tool.name,
                "query": query,
                "error": str(e),
            })
        
        # Try Semantic Scholar only if not rate-limited
        if not semantic_scholar_exhausted:
            ss_tool = SemanticScholarSearchTool()
            try:
                raw = ss_tool._run(query, max_results=8)
                payload = json.loads(raw)
                if payload.get("error"):
                    error_msg = payload["error"]
                    print(f"    ⚠️  {ss_tool.name}: {error_msg}")
                    source_errors.append(
                        {
                            "source": payload.get("source", ss_tool.name),
                            "query": query,
                            "error": error_msg,
                        }
                    )
                    # If rate-limited, don't try for remaining queries
                    if "429" in error_msg or "rate" in error_msg.lower():
                        semantic_scholar_exhausted = True
                        print(f"    📌 Semantic Scholar rate-limited. Skipping for remaining queries.")
                else:
                    papers_count = len(payload.get("papers", []))
                    print(f"    ✅ {ss_tool.name}: Found {papers_count} papers")
                    
                    for paper in payload.get("papers", []):
                        item = dict(paper)
                        item["query"] = query
                        if not is_topic_specific_match(item, topic):
                            print(f"       ❌ Filtered out: {item.get('title', '')[:50]}")
                            continue
                        item["relevance_score"] = paper_relevance_score(item, topic)
                        aggregated.append(item)
                        print(f"       ✅ Added (score={item['relevance_score']}): {item.get('title', '')[:50]}")
            except Exception as e:
                print(f"    ❌ {ss_tool.name}: Exception: {e}")
                source_errors.append({
                    "source": ss_tool.name,
                    "query": query,
                    "error": str(e),
                })
        
        # Add delay between queries to avoid rate limiting
        if idx < len(queries) - 1:
            import time
            time.sleep(1)
    
    deduped: dict[str, dict[str, Any]] = {}
    for paper in aggregated:
        key = (paper.get("url") or "").strip().lower() or (paper.get("title") or "").strip().lower()
        if not key:
            continue
        existing = deduped.get(key)
        if not existing or paper.get("relevance_score", 0) > existing.get("relevance_score", 0):
            deduped[key] = paper
    
    ranked_papers = sorted(
        deduped.values(),
        key=lambda item: (item.get("relevance_score", 0), item.get("citation_count", "0")),
        reverse=True,
    )
    
    final_papers = ranked_papers[:25]
    print(f"\n📊 Literature search complete: {len(final_papers)} unique papers after deduplication")
    print(f"📊 Total errors: {len(source_errors)}\n")
    
    return {"topic": topic, "queries": queries, "errors": source_errors, "papers": final_papers}


def compact_literature_bundle(source_bundle: dict[str, Any], max_papers: int = 8) -> dict[str, Any]:
    papers = []
    for paper in source_bundle.get("papers", [])[:max_papers]:
        papers.append(
            {
                "title": str(paper.get("title", "")),
                "source": str(paper.get("source", "")),
                "summary": str(paper.get("summary", ""))[:280],
                "url": str(paper.get("url", "")),
                "relevance_score": int(paper.get("relevance_score", 0) or 0),
            }
        )
    return {
        "topic": source_bundle.get("topic", ""),
        "queries": source_bundle.get("queries", [])[:4],
        "error_count": len(source_bundle.get("errors", [])),
        "top_papers": papers,
    }


def build_literature_screen_prompt(topic: str, compact_bundle: dict[str, Any]) -> str:
    return (
        f"Screen candidate papers for topic '{topic}'. "
        "Select the papers most likely to matter for a literature synthesis. "
        "Return strict JSON only with schema:\n"
        "{\n"
        '  "selected_indices": [0],\n'
        '  "rejected_indices": [1],\n'
        '  "selection_rationale": "string"\n'
        "}\n\n"
        "Rules:\n"
        "- choose at most 5 indices\n"
        "- prefer papers with direct topical relevance\n"
        "- if nothing fits, choose the closest 1-2 and explain why\n\n"
        f"Candidate bundle:\n{json.dumps(compact_bundle, ensure_ascii=True)}"
    )


def fallback_literature_screen_output(source_bundle: dict[str, Any]) -> LiteratureScreenOutput:
    selected = [paper.get("index", idx) for idx, paper in enumerate(source_bundle.get("papers", [])[:3])]
    return LiteratureScreenOutput(
        selected_indices=[int(index) for index in selected],
        rejected_indices=[],
        selection_rationale="Fallback selection based on heuristic ranking after screen stage error.",
    )


def screen_literature_candidates(flow: Any, source_bundle: dict[str, Any], compact_bundle: dict[str, Any]) -> LiteratureScreenOutput:
    prompt = build_literature_screen_prompt(flow.state.topic, compact_bundle)
    try:
        result = kickoff_with_retry(flow, "literature_screen", AgenticAiSystem().research_synthesizer(), prompt)
        screen_output = parse_model_output(result.raw, LiteratureScreenOutput)
    except Exception as exc:
        flow._persistence.stage_event(run_id(flow), "literature_screen", "fallback", f"Using heuristic screen after error: {exc}")
        screen_output = fallback_literature_screen_output(source_bundle)
    if not screen_output.selected_indices:
        screen_output.selected_indices = [paper.get("index", idx) for idx, paper in enumerate(source_bundle.get("papers", [])[:3])]
    return screen_output


def build_literature_deep_bundle(source_bundle: dict[str, Any], screen_output: LiteratureScreenOutput) -> dict[str, Any]:
    selected_indices = {int(index) for index in screen_output.selected_indices}
    selected_papers = []
    for idx, paper in enumerate(source_bundle.get("papers", [])):
        if idx not in selected_indices:
            continue
        selected_papers.append(
            {
                "index": idx,
                "title": str(paper.get("title", "")),
                "source": str(paper.get("source", "")),
                "summary": str(paper.get("summary", "")),
                "url": str(paper.get("url", "")),
                "relevance_score": int(paper.get("relevance_score", 0) or 0),
            }
        )
    return {
        "topic": source_bundle.get("topic", ""),
        "selected_indices": sorted(selected_indices),
        "selection_rationale": screen_output.selection_rationale,
        "papers": selected_papers,
        "selected_papers": selected_papers,
    }


def chunk_text(text: str, chunk_size: int = 4500) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    return [normalized[start : start + chunk_size] for start in range(0, len(normalized), chunk_size)]


def fetch_literature_papers(source_bundle: dict[str, Any], screen_output: LiteratureScreenOutput, max_papers: int = 4) -> list[dict[str, object]]:
    fetcher = PaperFullTextFetchTool()
    fetched_results: list[dict[str, object]] = []
    for index in screen_output.selected_indices[:max_papers]:
        try:
            paper = source_bundle.get("papers", [])[int(index)]
        except Exception:
            continue
        url = str(paper.get("url", ""))
        result = json.loads(fetcher._run(url))
        result["index"] = int(index)
        result["title"] = str(paper.get("title", ""))
        result["source"] = str(paper.get("source", ""))
        result["text_chunks"] = chunk_text(str(result.get("text", "")))
        fetched_results.append(result)
    return fetched_results


def build_paper_analysis_prompt(topic: str, paper: PaperFetchResult) -> str:
    chunks = paper.text_chunks or [""]
    return (
        f"Analyze the full text of paper '{paper.title}' for topic '{topic}'. "
        "Judge relevance and extract only evidence supported by the text. "
        "Return strict JSON only with schema:\n"
        "{\n"
        '  "index": 0,\n'
        '  "title": "string",\n'
        '  "source": "string",\n'
        '  "relevance_assessment": "string",\n'
        '  "key_findings": ["string"],\n'
        '  "limitations": ["string"],\n'
        '  "evidence_snippets": ["string"],\n'
        '  "summary": "string"\n'
        "}\n\n"
        "Rules:\n"
        "- use the full paper text chunks as evidence\n"
        "- focus on methods, findings, and limitations\n"
        "- keep the summary to 120-180 words\n\n"
        f"Text chunks JSON:\n{json.dumps(chunks, ensure_ascii=True)}"
    )


def build_literature_synthesis_prompt(topic: str, analyses: list[PaperAnalysisOutput]) -> str:
    return (
        f"Write a literature synthesis for topic '{topic}' based on the paper analyses below. "
        "Use only the evidence in the analyses and identify the main research gaps. "
        "Return strict JSON only with schema:\n"
        "{\n"
        '  "topic": "string",\n'
        '  "generated_at": "ISO datetime string",\n'
        '  "key_findings": [{"title":"string","source":"string","summary":"string","url":"string"}],\n'
        '  "synthesis": "string"\n'
        "}\n\n"
        "Rules:\n"
        "- use at most 5 key_findings\n"
        "- synthesis should be 150-220 words\n"
        "- prefer findings that appear across multiple paper analyses\n\n"
        f"Paper analyses JSON:\n{json.dumps([analysis.model_dump() for analysis in analyses], ensure_ascii=True)}"
    )


def fallback_literature_output(topic: str, source_bundle: dict[str, Any], reason: str) -> LiteratureResearchOutput:
    findings: list[PaperFinding] = []
    paper_source = source_bundle.get("papers", source_bundle.get("selected_papers", []))
    for paper in paper_source[:5]:
        findings.append(
            PaperFinding(
                title=str(paper.get("title", "")),
                source=str(paper.get("source", "")),
                summary=str(paper.get("summary", ""))[:700],
                url=str(paper.get("url", "")),
            )
        )
    if not findings:
        findings = [PaperFinding(title=f"{topic} research bundle", source="search-bundle", summary="No ranked papers were returned by the search tools.", url="")]
    queries = source_bundle.get("queries", [])
    return LiteratureResearchOutput(
        topic=topic,
        generated_at=datetime.now().isoformat(),
        key_findings=findings,
        synthesis=(
            "Deterministic literature synthesis generated from collected search results "
            f"after {reason}. Queries used: {', '.join(queries) or 'n/a'}."
        ),
    )


def run_literature_stage(flow: Any) -> LiteratureResearchOutput:
    flow._persistence.stage_event(run_id(flow), "literature", "running")
    try:
        crew_system = AgenticAiSystem()
        source_bundle = collect_literature_bundle(flow.state.topic)
        
        # Fallback: if no papers found, create placeholder papers
        if not source_bundle.get("papers"):
            errors_str = "\n".join([f"- {e['source']}: {e['error']} (query: {e['query']})" for e in source_bundle.get('errors', [])])
            error_msg = f"⚠️  No papers found from search. Errors:\n{errors_str}" if errors_str else "⚠️  No papers found from search (no errors logged)"
            print(f"\n{error_msg}\n")
            print("Using fallback placeholder paper for demonstration.\n")
            source_bundle["papers"] = [
                {
                    "title": f"Placeholder Paper 1 on {flow.state.topic}",
                    "source": "placeholder",
                    "summary": f"This is a placeholder. Unable to fetch papers on {flow.state.topic}. Check API connectivity and rate limits.",
                    "url": "",
                    "relevance_score": 50,
                }
            ]
        
        compact_bundle = compact_literature_bundle(source_bundle)
        screen_output = screen_literature_candidates(flow, source_bundle, compact_bundle)
        screen_artifact = store_literature_screen_output(flow.state.topic, screen_output)
        flow.state.literature_screen_output = screen_output
        flow.state.literature_screen_path = str(screen_artifact)
        screen_manifest = store_stage_artifact_manifest(
            "literature_screen",
            flow.state.topic,
            str(screen_artifact),
            "Literature screening selection stored",
            auxiliary_paths=[str(screen_artifact)],
            metadata={"selected_indices": screen_output.selected_indices},
        )
        flow.state.literature_screen_manifest_path = str(screen_manifest)
        flow._persistence.stage_event(run_id(flow), "literature_screen", "completed", f"artifact={screen_artifact}")

        fetched_results = fetch_literature_papers(source_bundle, screen_output)
        fetch_output = LiteratureFetchOutput(
            papers=[
                PaperFetchResult(
                    index=int(item.get("index", 0)),
                    title=str(item.get("title", "")),
                    source=str(item.get("source", "")),
                    source_url=str(item.get("source_url", "")),
                    resolved_pdf_url=str(item.get("resolved_pdf_url", "")),
                    page_count=int(item.get("page_count", 0) or 0),
                    text_length=len(str(item.get("text", ""))),
                    text_chunks=list(item.get("text_chunks", [])),
                    text_path="",
                    status=str(item.get("status", "")),
                    error=str(item.get("error", "")),
                )
                for item in fetched_results
            ]
        )
        fetch_dir, fetch_manifest = store_literature_fetch_output(flow.state.topic, fetched_results)
        for paper in fetch_output.papers:
            paper.text_path = str(Path(fetch_dir) / f"paper_{paper.index + 1:02d}.txt")
        flow.state.literature_fetch_output = fetch_output
        flow.state.literature_fetch_dir = str(fetch_dir)
        flow.state.literature_fetch_manifest_path = str(fetch_manifest)
        flow._persistence.stage_event(run_id(flow), "literature_fetch", "completed", f"artifact={fetch_manifest}")

        paper_analyses: list[PaperAnalysisOutput] = []
        for paper in fetch_output.papers:
            prompt = build_paper_analysis_prompt(flow.state.topic, paper)
            try:
                result = kickoff_with_retry(flow, "literature_analysis", crew_system.research_synthesizer(), prompt)
                paper_analysis = parse_model_output(result.raw, PaperAnalysisOutput)
            except Exception as exc:
                paper_analysis = PaperAnalysisOutput(
                    index=paper.index,
                    title=paper.title,
                    source=paper.source,
                    relevance_assessment=f"Fallback analysis after error: {exc}",
                    key_findings=[f"Full-text extraction available at {paper.text_path or paper.resolved_pdf_url}"],
                    limitations=[paper.error] if paper.error else [],
                    evidence_snippets=paper.text_chunks[:2],
                    summary=(
                        "Fallback analysis generated from the fetched paper text because the LLM "
                        f"failed with: {exc}"
                    ),
                )
            paper_analyses.append(paper_analysis)

        _analysis_dir, analysis_manifest = store_literature_analysis_output(flow.state.topic, paper_analyses)
        flow.state.literature_analysis_outputs = paper_analyses
        flow.state.literature_analysis_manifest_path = str(analysis_manifest)
        flow._persistence.stage_event(run_id(flow), "literature_analysis", "completed", f"artifact={analysis_manifest}")

        synthesis_prompt = build_literature_synthesis_prompt(flow.state.topic, paper_analyses)
        try:
            result = kickoff_with_retry(flow, "literature", crew_system.research_synthesizer(), synthesis_prompt)
            literature_output = parse_model_output(result.raw, LiteratureResearchOutput)
        except Exception as exc:
            flow._persistence.stage_event(run_id(flow), "literature", "fallback", f"Using deterministic synthesis after error: {exc}")
            literature_output = fallback_literature_output(
                flow.state.topic,
                {
                    "queries": source_bundle.get("queries", []),
                    "papers": [
                        {
                            "title": analysis.title,
                            "source": analysis.source,
                            "summary": analysis.summary,
                            "url": "",
                        }
                        for analysis in paper_analyses
                    ],
                },
                str(exc),
            )

        if not literature_output.topic:
            literature_output.topic = flow.state.topic
        if not literature_output.generated_at:
            literature_output.generated_at = datetime.now().isoformat()
        if not literature_output.key_findings:
            fallback_findings: list[PaperFinding] = []
            for paper in source_bundle.get("papers", [])[:5]:
                fallback_findings.append(
                    PaperFinding(
                        title=str(paper.get("title", "")),
                        source=str(paper.get("source", "")),
                        summary=str(paper.get("summary", ""))[:700],
                        url=str(paper.get("url", "")),
                    )
                )
            literature_output.key_findings = fallback_findings
        if not literature_output.synthesis:
            literature_output.synthesis = "Synthesis generated from ranked literature results. Review key_findings and refine topic keywords if needed."

        flow.state.literature_output = literature_output
        artifact = store_literature_output(flow.state.topic, literature_output)
        flow.state.literature_artifact_path = str(artifact)
        literature_manifest = store_stage_artifact_manifest(
            "literature",
            flow.state.topic,
            str(artifact),
            "Literature synthesis stored",
            auxiliary_paths=[str(artifact)],
            metadata={"key_findings": len(literature_output.key_findings)},
        )
        flow.state.literature_manifest_path = str(literature_manifest)
        finding_preview = "\n".join([f"- {item.title} ({item.source})" for item in literature_output.key_findings[:5]])
        preview = f"Stored literature artifact: {artifact}\nTop findings:\n{finding_preview or '- no findings returned'}\n\nSynthesis: {literature_output.synthesis[:350]}"
        flow._approval_gate("literature", preview)
        flow._persistence.stage_event(run_id(flow), "literature", "completed", f"artifact={artifact}")
        ui_update_queue.put({"type": "stage_completed", "stage": "literature", "timestamp": datetime.now().isoformat()})
        return literature_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected

        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "literature", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "literature", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise
