import json
import csv
from pathlib import Path
from typing import Dict, List, Optional, Any

def load_successful_instances(oracle_results_file: Path) -> set:
    """
    Load instances that passed the fix_patch test from oracle_results.jsonl.
    
    Returns:
        Set of (repo, base_commit) tuples that passed
    """
    successful = set()
    
    if not oracle_results_file.exists():
        print(f"[WARN] Oracle results file not found: {oracle_results_file}")
        print("[WARN] Will process all instances")
        return None
    
    with open(oracle_results_file) as f:
        for line in f:
            if line.strip():
                result = json.loads(line)
                if result.get("fix_patch") == "PASS":
                    repo = result.get("repo")
                    base_commit = result.get("base_commit")
                    if repo and base_commit:
                        successful.add((repo, base_commit))
    
    print(f"[INFO] Loaded {len(successful)} successful instances from oracle_results.jsonl")
    return successful


def load_oracle_tasks(ORACLE_ROOT, successful_filter: set = None,) -> List[Dict[str, Any]]:
    """
    Load tasks from Oracle Lite dataset.
    
    Args:
        successful_filter: Optional set of (repo, base_commit) tuples to filter by
    
    Returns:
        List of task dictionaries containing oracle_lite data
    """
    tasks = []
    filtered_count = 0
    print(f"Loading tasks from Oracle dataset at {ORACLE_ROOT} ...")
    
    index_csv = ORACLE_ROOT / "index.csv"
    if not index_csv.exists():
        print(f"[ERROR] index.csv not found at {index_csv}")
        return tasks
    
    with open(index_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            repo_folder = ORACLE_ROOT / row['repo_folder']
            instances_dir = repo_folder / "instances"
            
            if not instances_dir.exists():
                print(f"[WARN] Instances directory not found: {instances_dir}")
                continue
            
            for inst_dir in instances_dir.iterdir():
                if inst_dir.is_dir():
                    oracle_file = inst_dir / "oracle_lite.json"
                    if oracle_file.exists():
                        try:
                            with open(oracle_file) as jf:
                                data = json.load(jf)
                                features = data.get("features", {})
                                
                                instance_id = features.get("instance_id")
                                repo = features.get("repo")
                                base_commit = features.get("base_commit")
                                
                                if not repo or not base_commit or not instance_id:
                                    print(f"[WARN] Missing required fields in {oracle_file}")
                                    continue
                                
                                # Filter by successful instances if filter is provided
                                if successful_filter is not None:
                                    if (repo, base_commit) not in successful_filter:
                                        filtered_count += 1
                                        continue  # Skip this instance
                                
                                # Extract all relevant context
                                task = {
                                    "instance_id": instance_id,
                                    "repo": repo,
                                    "base_commit": base_commit,
                                    # Problem descriptions (natural language only)
                                    "pull_request_text": features.get("pull_request_text", ""),
                                    "issue_text": features.get("issue_text", ""),
                                    "natural_brief": features.get("natural-brief", ""),
                                    "natural_detailed": features.get("natural-detailed", ""),
                                    # Repository context (non-patch data)
                                    "readmes": features.get("readmes", []),
                                    "files": features.get("files", []),
                                    "new_components": features.get("new_components", []),
                                    # EXCLUDED: "patch", "test_patch", "non_py_patch", "patch-detailed", "patch-brief"
                                }
                                
                                tasks.append(task)
                                
                        except Exception as e:
                            print(f"[ERROR] Failed to load {oracle_file}: {e}")
                            continue
    
    if successful_filter is not None:
        print(f"Filtered out {filtered_count} instances that didn't pass fix_patch test.")
    print(f"Found {len(tasks)} tasks from Oracle dataset.")
    return tasks
