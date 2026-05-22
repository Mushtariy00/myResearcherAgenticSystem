"""Agentmemory MCP integration for supervisor flow.

This module provides wrappers around agentmemory tools to save and recall
research context across sessions, enabling persistent memory of findings,
methods, and approvals.
"""
from __future__ import annotations

from typing import Any


def save_literature_findings(
    topic: str,
    run_id: str,
    papers: list[dict[str, Any]],
    screening_rationale: str | None = None,
) -> None:
    """Save literature search findings to memory.
    
    Args:
        topic: Research topic
        run_id: Unique run identifier for traceability
        papers: List of screened papers (title, source, relevance)
        screening_rationale: Why these papers were selected
    """
    if not papers:
        return
    
    content = (
        f"Literature findings for topic '{topic}' (run: {run_id}):\n"
        f"Total papers selected: {len(papers)}\n"
        f"Papers:\n"
    )
    for paper in papers[:5]:  # Top 5 only to keep size reasonable
        title = paper.get("title", "Unknown")
        source = paper.get("source", "unknown_source")
        content += f"  - {title} ({source})\n"
    
    if screening_rationale:
        content += f"\nScreening rationale: {screening_rationale}"
    
    try:
        # Save to agentmemory via CLI tool (this would be called from within session)
        # In actual implementation, this integrates with the copilot CLI's memory system
        _memory_save(
            content=content,
            type="pattern",  # Pattern because it's a consistent research approach
            concepts=f"literature,research,{topic}",
            files=f"run_{run_id}",
        )
    except Exception as e:
        # Memory save failure should not block the pipeline
        print(f"Warning: Failed to save literature findings to memory: {e}")


def save_pdf_fetch_results(
    topic: str,
    run_id: str,
    total_attempted: int,
    success_count: int,
    fetch_strategies: list[str] | None = None,
) -> None:
    """Save PDF fetch results and strategies to memory.
    
    Args:
        topic: Research topic
        run_id: Unique run identifier
        total_attempted: Total papers attempted
        success_count: Successfully fetched PDFs
        fetch_strategies: List of strategies used (arXiv, Unpaywall, OpenAlex, etc.)
    """
    success_rate = (success_count / total_attempted * 100) if total_attempted > 0 else 0
    
    content = (
        f"PDF Fetch results for '{topic}' (run: {run_id}):\n"
        f"Success rate: {success_rate:.1f}% ({success_count}/{total_attempted})\n"
    )
    
    if fetch_strategies:
        content += f"Strategies used: {', '.join(set(fetch_strategies))}\n"
    
    content += (
        f"\nLessons: "
        f"Success rate {'high' if success_rate > 70 else 'moderate' if success_rate > 50 else 'low'}. "
        f"Consider {'expanding strategies' if success_rate < 50 else 'current approach working well'}."
    )
    
    try:
        _memory_save(
            content=content,
            type="pattern",
            concepts=f"pdf-fetch,open-access,{topic}",
            files=f"run_{run_id}",
        )
    except Exception as e:
        print(f"Warning: Failed to save PDF fetch results to memory: {e}")


def save_method_decision(
    topic: str,
    run_id: str,
    research_gaps: list[str] | None = None,
    selected_method: str | None = None,
    rationale: str | None = None,
    artifact_path: str | None = None,
) -> None:
    """Save method decision and gap analysis to memory.
    
    Args:
        topic: Research topic
        run_id: Unique run identifier
        research_gaps: Key gaps identified from literature
        selected_method: Name of selected method/approach
        rationale: Why this method was chosen
        artifact_path: Path to method artifact for reference
    """
    content = f"Method decision for '{topic}' (run: {run_id}):\n"
    
    if research_gaps:
        content += f"Research gaps identified:\n"
        for gap in research_gaps[:5]:
            content += f"  - {gap}\n"
    
    if selected_method:
        content += f"Selected method: {selected_method}\n"
    
    if rationale:
        content += f"Rationale: {rationale}\n"
    
    if artifact_path:
        content += f"Method artifact: {artifact_path}\n"
    
    try:
        _memory_save(
            content=content,
            type="decision",  # Decision because it's an approved research direction
            concepts=f"method,gap-analysis,{topic}",
            files=artifact_path or f"run_{run_id}",
        )
    except Exception as e:
        print(f"Warning: Failed to save method decision to memory: {e}")


def recall_relevant_research(
    topic: str,
    stage: str | None = None,
    limit: int = 3,
) -> str:
    """Recall relevant research findings from prior sessions.
    
    Args:
        topic: Research topic to query
        stage: Stage name for context (literature, method, coding)
        limit: Max results to return
        
    Returns:
        Formatted context string to inject into prompts, or empty string if no results
    """
    query = f"{topic} research findings"
    if stage:
        query += f" {stage}"
    
    try:
        # This would use memory recall tools
        # In actual implementation, integrates with copilot CLI memory system
        results = _memory_recall(query, limit=limit)
        
        if not results:
            return ""
        
        context = "Previous research context:\n"
        for result in results:
            context += f"- {result[:200]}...\n"  # Truncate to keep reasonable
        
        return context
    except Exception as e:
        # Recall failure should not block the pipeline
        print(f"Warning: Failed to recall research context: {e}")
        return ""


def save_lesson_learned(
    content: str,
    topic: str | None = None,
    confidence: float = 0.7,
    context: str | None = None,
) -> None:
    """Save a lesson learned with confidence score.
    
    Args:
        content: The lesson to save (what worked, what to avoid, etc.)
        topic: Optional topic this lesson applies to
        confidence: Confidence score 0.0–1.0 (default: 0.7)
        context: When/where this lesson applies
    """
    try:
        _memory_lesson_save(
            content=content,
            confidence=confidence,
            context=context or f"Research on {topic or 'general topics'}",
            project=topic or "agentic-research-system",
            tags=f"lesson,{topic or 'general'}",
        )
    except Exception as e:
        print(f"Warning: Failed to save lesson learned: {e}")


# =============================================================================
# Internal wrappers (would integrate with copilot CLI tools in production)
# =============================================================================

def _memory_save(
    content: str,
    type: str = "fact",
    concepts: str | None = None,
    files: str | None = None,
) -> None:
    """Internal wrapper for agentmemory-memory_save tool."""
    # In production, this would call:
    # agentmemory-memory_save(
    #     content=content,
    #     type=type,
    #     concepts=concepts,
    #     files=files,
    # )
    pass


def _memory_recall(
    query: str,
    limit: int = 10,
) -> list[str]:
    """Internal wrapper for agentmemory-memory_recall tool."""
    # In production, this would call:
    # results = agentmemory-memory_recall(
    #     query=query,
    #     limit=limit,
    # )
    # return results
    return []


def _memory_lesson_save(
    content: str,
    confidence: float = 0.5,
    context: str | None = None,
    project: str | None = None,
    tags: str | None = None,
) -> None:
    """Internal wrapper for agentmemory-memory_lesson_save tool."""
    # In production, this would call:
    # agentmemory-memory_lesson_save(
    #     content=content,
    #     confidence=confidence,
    #     context=context,
    #     project=project,
    #     tags=tags,
    # )
    pass
