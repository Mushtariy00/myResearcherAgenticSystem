#!/usr/bin/env python3
import json
from src.agentic_ai_system.tools.literature_tools import ArxivSearchTool, SemanticScholarSearchTool

# Test ArxivSearchTool
print("Testing ArxivSearchTool with query: 'monocular depth estimation'")
arxiv_tool = ArxivSearchTool()
arxiv_result = arxiv_tool._run("monocular depth estimation", max_results=5)
arxiv_data = json.loads(arxiv_result)
print(f"ArXiv result: {json.dumps(arxiv_data, indent=2)[:500]}")
print(f"Papers found: {len(arxiv_data.get('papers', []))}\n")

# Test SemanticScholarSearchTool  
print("Testing SemanticScholarSearchTool with query: 'monocular depth estimation'")
ss_tool = SemanticScholarSearchTool()
ss_result = ss_tool._run("monocular depth estimation", max_results=5)
ss_data = json.loads(ss_result)
print(f"Semantic Scholar result: {json.dumps(ss_data, indent=2)[:500]}")
print(f"Papers found: {len(ss_data.get('papers', []))}")
