#!/usr/bin/env python3
"""
Documenter for FEA-Bench

This script generates documents from oracle_lite data WITHOUT
using test patches or golden patches.

Usage:
    python documenter.py --model ["gemini", "deepseek"]

Requirements:
    - GEMINI_API_KEY environment variable must be set
    - pip install google-genai
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import argparse

from transformers import pipeline, set_seed

from utils.prompt_builder import build_prompt
from utils.load_instances import load_successful_instances, load_oracle_tasks
from utils.generate_patch import generate_doc, save_doc

# ----- Configuration -----
ROOT = Path("/storage/ice1/shared/ece8803cai/team14/FEA-Bench")
ORACLE_ROOT = ROOT / "feabench-data" / "repo_data_oracle_lite"
ORACLE_RESULTS_FILE = ROOT / "oracle_results.jsonl"
output_dir_general = "/storage/ice1/shared/ece8803cai/team14/docs"
results_file_general = "/storage/ice1/shared/ece8803cai/team14"

# Gemini Configuration
GEMINI_MODEL = "gemini-2.5-flash" 
# DeepSeek Config
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_INSTRUCTION = """You are an expert software engineer tasked with creating documents that other software engineers can use to implement new features.

Given a problem description and repository context, generate a detailed, specific document explaining how to implement the requested feature. Think about what features would be useful for you to have if you were going to code the feature. 

Your document should:
1. Be as specific possible without any ambiguity. Another software engineer should be able to clearly follow the steps outlined in your document to implement the feature
2. Synthesize a large amount of context while retaining as much valuable information as possible
3. Make clear to another engineer how to follow the coding style of the existing codebase
4. You may provide a repository overview, a clear implementation plan, pseudo-code in relevant files, or any other information that you believe would be helpful """


MAX_INSTANCES = None  # Set to a number like 5 for testing, or None for all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=['gemini', 'deepseek'], help="Define the documenter model.")
    args = ap.parse_args()

    """Main execution function."""
    print("="*60)
    print("Documenter for FEA-Bench (FILTERED)")
    print("="*60)

    OUTPUT_DIR = Path(f"{output_dir_general}/documenter-oracle-{args.model}")
    print(f"Output Directory: {OUTPUT_DIR}")
    RESULTS_FILE = Path(f"{results_file_general}/documenter_{args.model}_results.jsonl")
    print(f"Results File: {RESULTS_FILE}")
    print("="*60)

    # Check for API keys
    if args.model == "gemini":
        model = GEMINI_MODEL
        print(f"Using: {model}")
        if not os.environ.get("GEMINI_API_KEY"):
            print("[ERROR] GEMINI_API_KEY environment variable not set!")
            print("Please set it with: export GEMINI_API_KEY='your-api-key'")
            return

    if args.model == "deepseek":
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
            "doc_generated": False,
            "doc_path": None,
            "error": None,
        }
        
        try:
            # Build prompt
            prompt = build_prompt(task, "documenter")
            repo_slug = repo.replace("/", "__")
            with open(f"documenter_prompts/{repo_slug}.txt", "w") as f:
                f.write(prompt)
            
            # Generate docoument
            doc_text = generate_doc(prompt, instance_id, args.model, model, SYSTEM_INSTRUCTION)
            
            if doc_text:
                # Save document
                doc_path = save_doc(doc_text, task, OUTPUT_DIR)
                result["doc_generated"] = True
                result["doc_path"] = doc_path
                print(f"  [SUCCESS] Document generated for {instance_id}")
            else:
                result["error"] = "Failed to generate document"
                print(f"  [FAILED] Could not generate document for {instance_id}")
        
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
    successful = sum(1 for r in results if r["doc_generated"])
    failed = total - successful
    
    print(f"\nTotal instances processed: {total}")
    print(f"Successful doc generation: {successful} ({100*successful/total if total > 0 else 0:.1f}%)")
    print(f"Failed: {failed} ({100*failed/total if total > 0 else 0:.1f}%)")
    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"Documents saved to: {OUTPUT_DIR}")
    print("\n" + "="*60)


if __name__ == "__main__":
    main()

