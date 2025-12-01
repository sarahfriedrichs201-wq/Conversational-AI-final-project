#!/usr/bin/env python3
"""
Coder Patcher for FEA-Bench

This script generates fix patches from oracle_lite data WITHOUT
using test patches or golden patches.

Usage:
    python coder.py --model ["gemini", "deepseek"]

Requirements:
    - GEMINI_API_KEY environment variable must be set
    - pip install google-genai
"""
import json
import os
from pathlib import Path
from datetime import datetime
import argparse

from utils.prompt_builder import build_prompt
from utils.load_instances import load_successful_instances, load_oracle_tasks
from utils.generate_patch import generate_patch, save_patch

# ----- Configuration -----
ROOT = Path("/storage/ice1/shared/ece8803cai/team14/FEA-Bench")
ORACLE_ROOT = ROOT / "feabench-data" / "repo_data_oracle_lite"
ORACLE_RESULTS_FILE = ROOT / "oracle_results.jsonl"
INPUT_DOCS = "/storage/ice1/shared/ece8803cai/team14/docs"
output_dir_general = "/storage/ice1/shared/ece8803cai/team14/patches"
results_file_general = "/storage/ice1/shared/ece8803cai/team14"

# Gemini Configuration
GEMINI_MODEL = "gemini-2.5-flash" 
# DeepSeek Config
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_INSTRUCTION = """You are an expert software engineer tasked with implementing new features in codebases.

You will be given a document written by another export software eningeer. This document should contain sufficient information to implement a new feature into the codebase. Using this document, generate a complete git diff format patch to implement the requested feature.

Your patch should:
1. Be in unified diff format (git diff style) that can be applied with `git apply`
2. Include all necessary changes to implement the feature
3. Follow the coding style of the existing codebase
4. Be syntactically correct and complete
5. Use proper git index hashes - either use real SHA-1 hashes (40 hex characters) or omit the 'index' line entirely
6. DO NOT use placeholder hashes like '1234567' or 'abcdefg' - these will cause the patch to fail

IMPORTANT: Each file diff should follow this exact format:
diff --git a/path/to/file.py b/path/to/file.py
index <old-hash>..<new-hash> <mode>   <- Use real hashes OR omit this line completely
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -line,count +line,count @@ optional context
 context lines
-removed lines
+added lines

Output ONLY the git diff patch, starting with "diff --git" lines. Do not provide any explanations - only relevant code.

"""


MAX_INSTANCES = None  # Set to a number like 5 for testing, or None for all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--documenter", choices=['gemini', 'deepseek'], help="Define the documenter model.")
    ap.add_argument("--coder", choices=['gemini', 'deepseek'], help="Define the coder model.")
    args = ap.parse_args()

    """Main execution function."""
    print("="*60)
    print("Coder Patcher for FEA-Bench (FILTERED)")
    print("="*60)

    OUTPUT_DIR = Path(f"{output_dir_general}/coder-{args.coder}-documenter-{args.documenter}")
    print(f"Output Directory: {OUTPUT_DIR}")
    RESULTS_FILE = Path(f"{results_file_general}/coder_{args.coder}-documenter-{args.documenter}_results.jsonl")
    print(f"Results File: {RESULTS_FILE}")
    print("="*60)

    # Check for API keys
    if args.coder == "gemini":
        model = GEMINI_MODEL
        print(f"Using: {model}")
        if not os.environ.get("GEMINI_API_KEY"):
            print("[ERROR] GEMINI_API_KEY environment variable not set!")
            print("Please set it with: export GEMINI_API_KEY='your-api-key'")
            return

    if args.coder == "deepseek":
        model = DEEPSEEK_MODEL
        print(f"Using: {model}")
        if not os.environ.get("DEEPSEEK_API_KEY"):
            print("[ERROR] DEEPSEEK_API_KEY environment variable not set!")
            print("Please set it with: export DEEPSEEK_API_KEY='your-api-key'")
            return
    
    # Load successful instances filter
    successful_filter = load_successful_instances(ORACLE_RESULTS_FILE)
    if successful_filter:
        print(f"[INFO] Will only process {len(successful_filter)} instances with fix_patch=PASS")
    
    # Create output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Load tasks with filter
    tasks = load_oracle_tasks(ORACLE_ROOT, successful_filter)
    
    if not tasks:
        print("[ERROR] No tasks loaded. Exiting.")
        return
    
    # Limit tasks if specified
    if MAX_INSTANCES is not None:
        tasks = tasks[:MAX_INSTANCES]
        print(f"[INFO] Limited to {MAX_INSTANCES} instances for testing")
    
    # Process each task
    print("="*60)
    print("Beginning Task Processing")
    print("="*60)
    results = []
    for i, task in enumerate(tasks, 1):
        instance_id = task["instance_id"]
        repo = task["repo"]
        base_commit = task["base_commit"]
        
        print(f"\n[{i}/{len(tasks)}] Processing {instance_id}")
        print(f"  Repo: {repo}")
        print(f"  Base Commit: {base_commit}")
        
        result = {
            "instance_id": instance_id,
            "repo": repo,
            "base_commit": base_commit,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "patch_generated": False,
            "patch_path": None,
            "error": None,
        }

        try:
            # Build prompt
            repo_slug = repo.replace("/", "__")
            file_path = f"{INPUT_DOCS}/documenter-oracle-{args.documenter}/{repo_slug}/{instance_id}.txt"

            # Read document produced by the documenter
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Document not found: {file_path}")

            with open(file_path, "r", encoding="utf-8") as f:
                doc = f.read()

            if not doc.strip():
                raise ValueError(f"Empty document at {file_path}")

            prompt_parts = []

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

            prompt = doc + "".join(prompt_parts)

            with open(f"coder_prompts/{repo_slug}.txt", "w") as f:
                f.write(prompt)
            
            # Generate patch
            patch_text = generate_patch(prompt, instance_id, args.coder, model, SYSTEM_INSTRUCTION)
            
            if patch_text:
                # Save patch
                patch_path = save_patch(patch_text, task, OUTPUT_DIR)
                result["patch_generated"] = True
                result["patch_path"] = patch_path
                print(f"  [SUCCESS] Patch generated for {instance_id}")
            else:
                result["error"] = "Failed to generate patch"
                print(f"  [FAILED] Could not generate patch for {instance_id}")
        
        except Exception as e:
            result["error"] = str(e)
            print(f"  [ERROR] Exception for {instance_id}: {e}")
        
        # Save result incrementally
        results.append(result)
        with open(RESULTS_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")
    
    # Print summary
    print("\n" + "="*60)
    print("=== SUMMARY ===")
    print("="*60)
    
    total = len(results)
    successful = sum(1 for r in results if r["patch_generated"])
    failed = total - successful
    
    print(f"\nTotal instances processed: {total}")
    print(f"Successful patch generation: {successful} ({100*successful/total if total > 0 else 0:.1f}%)")
    print(f"Failed: {failed} ({100*failed/total if total > 0 else 0:.1f}%)")
    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"Patches saved to: {OUTPUT_DIR}")
    print("\n" + "="*60)


if __name__ == "__main__":
    main()

