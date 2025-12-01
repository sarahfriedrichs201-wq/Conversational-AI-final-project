import argparse
import json
from pathlib import Path

def build_prompt(task: dict, role: str) -> str:
    """
    Build a prompt from task data.
    
    Args:
        task: Task dictionary with oracle_lite data
        
    Returns:
        Formatted prompt string
    """
    feat = task
    prompt_parts = []
    
    # Add problem description from oracle data
    prompt_parts.append("# Problem Description\n\n")
    
    pull_request_text = feat.get("pull_request_text")
    if pull_request_text:
        prompt_parts.append(f"## Pull Request\n{pull_request_text}\n\n")
    
    issue_text = feat.get("issue_text")
    if issue_text:
        prompt_parts.append(f"## Issue\n{issue_text}\n\n")
    
    # if task["natural_detailed"]:
    #     prompt_parts.append(f"## Feature Description\n{task['natural_detailed']}\n\n")
    # elif task["natural_brief"]:
    #     prompt_parts.append(f"## Feature Description\n{task['natural_brief']}\n\n")
    
    # Add oracle JSON metadata
    prompt_parts.append("\n# Repository Information\n\n")
    
    # Add README content (limited to first 2 for brevity)
    readmes = feat.get("readmes") 
    if readmes:
        prompt_parts.append("## Repository Documentation\n")
        for readme in readmes[:2]:
            file_path = readme.get("file", "README")
            content = readme.get("content", "")
            # Limit content length
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            prompt_parts.append(f"### {file_path}\n```\n{content}\n```\n\n")
    
    # Add new component signatures
    new_components = feat.get("new_components")
    if new_components:
        prompt_parts.append("## New Components to Implement\n")
        for comp in new_components:
            file_path = comp.get("file", "unknown")
            prompt_parts.append(f"### File: {file_path}\n")
            for component in comp.get("components", []):
                comp_type = component.get("type", "function")
                signature = component.get("signature", "")
                doc = component.get("doc", "")
                name = component.get("name", "")
                
                prompt_parts.append(f"**{comp_type.capitalize()}**: `{name}`\n")
                if signature:
                    prompt_parts.append(f"```python\n{signature}\n```\n")
                if doc:
                    prompt_parts.append(f"Description: {doc}\n")
                prompt_parts.append("\n")
    
    # Add relevant file snippets (limited)
    files = feat.get("files") 
    if files:
        prompt_parts.append("## Relevant Code Files\n")
        for file_info in files[:3]:  # Limit to first 3 files
            file_path = file_info.get("file", "unknown")
            content = file_info.get("content", "")
            # Limit content length
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            prompt_parts.append(f"### {file_path}\n```\n{content}\n```\n\n")
    
    # Final instruction
    prompt_parts.append("\n# Task\n")
    if role == "baseline":
        prompt_parts.append("Generate a complete git diff format patch to implement the feature described above.\n")
        prompt_parts.append("CRITICAL OUTPUT FORMAT REQUIREMENTS:\n\n")
        prompt_parts.append("1. Output ONLY the raw patch content - NO markdown code blocks\n\n")
        prompt_parts.append("2. Do NOT wrap output in ``` or ```\n")
        prompt_parts.append("3. Start your response IMMEDIATELY with patch content\n")
        prompt_parts.append("4. Do NOT include 'index <hash>..<hash>' lines\n")
        prompt_parts.append("5. First line should be 'diff --git' or '---' (not triple backticks)\n")
        prompt_parts.append("EXAMPLE OF CORRECT FORMAT:\n")
        prompt_parts.append("diff --git a/file.py b/file.py\n")
        prompt_parts.append("--- a/file.py\n")
        prompt_parts.append("+++ b/file.py\n")
        prompt_parts.append("@@ -1,3 +1,4 @@\n")
        prompt_parts.append(" existing line\n")
        prompt_parts.append("+new line\n")
        prompt_parts.append("\n")
        prompt_parts.append("WRONG - Do NOT do this:\n")
        prompt_parts.append("\n")
        prompt_parts.append("diff --git a/file.py b/file.py\n")
        prompt_parts.append("```\n")
        prompt_parts.append("The patch must be ready to apply with `git apply` without any preprocessing.\n")
    if role == "documenter":
        prompt_parts.append("Generate a clear, instructional document explaining how to generate the feature described above.\n")
    
    return "".join(prompt_parts)