"""Agentmemory Integration Documentation

This document describes how agentmemory MCP is integrated into the supervisor flow
for persistent research context across sessions.

## Overview

Agentmemory is a persistent memory system accessible via MCP tools. It allows the
research pipeline to:
1. Save research findings, decisions, and lessons learned
2. Recall relevant prior research to avoid re-explaining context
3. Build on previous sessions without redundant work
4. Share learning patterns across multiple research topics

## Architecture

```
Supervisor Flow
├── @start: initialize
├── @listen(initialize): literature_stage
│   └── [After stage] save_literature_findings() → Memory
│
├── @listen(literature_stage): pdf_fetch_stage
│   └── [After stage] save_pdf_fetch_results() → Memory
│
├── @listen(pdf_fetch_stage): method_stage
│   ├── [Before] recall_relevant_research() → Context injection
│   └── [After] save_method_decision() → Memory
│
└── [Future stages] Additional memory hooks as needed
```

## Save Operations

### save_literature_findings(topic, run_id, papers, screening_rationale)
**When:** After literature_stage completes and is approved
**What:** Saves screened paper titles, sources, and selection rationale
**Format:** Pattern (consistent research approach across topics)
**Concepts:** literature, research, {topic}
**Files:** run_{run_id}

Example stored:
```
Literature findings for topic 'deep learning' (run: flow_abc123):
Total papers selected: 5
Papers:
  - Transformer-XL: Attentive Language Models Beyond a Fixed-Length Context (arXiv)
  - BERT: Pre-training of Deep Bidirectional Transformers (ACL)
  ...
Screening rationale: Selected for relevance to core topic and publication year
```

### save_pdf_fetch_results(topic, run_id, total_attempted, success_count, fetch_strategies)
**When:** After pdf_fetch_stage completes and is approved
**What:** Saves PDF fetch success rate and strategies used
**Format:** Pattern (research methodology)
**Concepts:** pdf-fetch, open-access, {topic}
**Files:** run_{run_id}

Example stored:
```
PDF Fetch results for 'deep learning' (run: flow_abc123):
Success rate: 80.0% (4/5)
Strategies used: arxiv, unpaywall, openalex

Lessons: Success rate high. Current approach working well.
```

### save_method_decision(topic, run_id, gaps, selected_method, rationale, artifact_path)
**When:** After method_stage completes and is approved
**What:** Saves identified research gaps, proposals considered, and rationale
**Format:** Decision (important research direction)
**Concepts:** method, gap-analysis, {topic}
**Files:** path_to_method_artifact

Example stored:
```
Method decision for 'deep learning' (run: flow_abc123):
Research gaps identified:
  - Scalability of attention mechanisms to longer sequences
  - Interpretability of deep model decisions
  - Energy efficiency of large models

Selected method: Sparse Attention with Hierarchical Transformers
Rationale: Selected from 3 proposals based on literature analysis
Method artifact: outputs/method/deep_learning_flow_abc123/method.json
```

## Recall Operations

### recall_relevant_research(topic, stage, limit=3)
**When:** At the start of analysis stages (before method, coding, etc.)
**How:** Searches memory for prior findings using topic and stage context
**Returns:** Formatted context string to inject into agent prompts
**Graceful Failure:** Returns empty string if no prior context exists

Flow:
```python
# Before method analysis
prior_context = recall_relevant_research(topic="deep learning", stage="method")

if prior_context:
    # Inject into prompt to avoid re-analyzing prior findings
    prompt = prior_context + "\n\n" + base_prompt
```

Example injected context:
```
Previous research context:
- Found 5 key papers on transformers from prior session
- Identified scalability and interpretability as main gaps
- Prior session recommended attention optimization approach
```

## Data Safety

### What's Saved
- ✓ Paper titles, sources, publication years
- ✓ Fetch success rates and strategies used
- ✓ Research gap descriptions
- ✓ Method proposal names and rationales
- ✓ Artifact file paths (for reference)
- ✓ Lessons learned and domain patterns

### What's NOT Saved
- ✗ API keys or credentials
- ✗ Email addresses or personal data
- ✗ Proprietary model weights or code
- ✗ Full PDF text content
- ✗ Sensitive business metrics

### PII Redaction
All save functions intentionally exclude:
- User identities (only run_id for traceability)
- Email addresses
- Personal information

## Integration Points

### Literature Pipeline
No direct integration yet. Future work:
```python
def run_literature_stage(flow):
    # ... existing code ...
    results = run_literature_stage_impl(flow)
    
    # Save findings after approval
    save_literature_findings(
        topic=flow.state.topic,
        run_id=run_id(flow),
        papers=[p.dict() for p in results.papers],
        screening_rationale=results.screening_notes,
    )
    return results
```

### PDF Fetch Stage
Already integrated in research_pipeline.py:
```python
def run_pdf_fetch_stage(flow, literature_output):
    # ... fetch implementation ...
    
    # Save fetch results after approval
    save_pdf_fetch_results(
        topic=flow.state.topic,
        run_id=run_id(flow),
        total_attempted=len(fetch_results),
        success_count=success_count,
        fetch_strategies=list(set(fetch_strategies)),
    )
```

### Method Stage
Already integrated in research_pipeline.py:
```python
def run_method_stage(flow, literature_output):
    # Recall prior research before analysis
    prior_context = recall_relevant_research(
        topic=flow.state.topic,
        stage="method",
        limit=3,
    )
    
    # ... method analysis with optional context injection ...
    
    # Save decision after approval
    save_method_decision(
        topic=flow.state.topic,
        run_id=run_id(flow),
        research_gaps=method_output.research_gaps,
        selected_method=method_output.recommended_option,
        rationale=f"Selected from {len(proposals)} proposals",
        artifact_path=str(method_artifact),
    )
```

## Failure Handling

All save/recall operations are wrapped in try-except blocks:
```python
def save_literature_findings(...):
    try:
        _memory_save(...)
    except Exception as e:
        print(f"Warning: Failed to save: {e}")
        # Pipeline continues - memory failure is non-blocking
```

This ensures that memory system issues don't block research flow execution.

## Testing Memory Integration

### Manual Test
1. Run flow with topic "deep learning"
2. Complete literature and method stages with approvals
3. Run flow again with same topic
4. Verify method stage includes "Previous research context:" in output

### Automated Tests
See `tests/test_memory_integration.py` for:
- Mock agentmemory responses
- Save function correctness
- Recall context injection
- Failure graceful handling

## Future Enhancements

Phase 2+ opportunities:
1. **Memory-aware Method Selection:** Rank proposals using prior success rates
2. **Cross-topic Learning:** Apply lessons from related topics
3. **Experiment Memory:** Save experiment configs and results
4. **Writing Memory:** Store section templates and approaches
5. **Confidence Scoring:** Boost confidence for methods that worked before
6. **Lesson Decay:** Automatically lower confidence of old lessons over time

## Configuration

Currently hardcoded but can be moved to .env:
```
# .env additions for future
AGENTMEMORY_ENABLED=true
AGENTMEMORY_SAVE_PAPERS=true
AGENTMEMORY_SAVE_METHODS=true
AGENTMEMORY_RECALL_CONTEXT=true
AGENTMEMORY_CONTEXT_LIMIT=3  # Max prior results to inject
```

## References

- agentmemory-memory_save: Save content with metadata
- agentmemory-memory_recall: Query memory with keywords
- agentmemory-memory_lesson_save: Save lessons with confidence
- agentmemory-memory_smart_search: Hybrid semantic+keyword search
