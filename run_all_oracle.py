import json
import csv
import os
import subprocess
from pathlib import Path

# ----- Paths -----
ROOT = Path("/storage/ice1/shared/ece8803cai/team14/FEA-Bench")
ORACLE_ROOT = ROOT / "feabench-data" / "repo_data_oracle_lite"
REPO_ROOT = ROOT / "repos_all"         
RESULTS_PATH = ROOT / "oracle_results.jsonl"

REPO_ROOT.mkdir(exist_ok=True, parents=True)

def run_cmd(cmd, cwd, env=None):
    """Run a shell command, return (ok, output)."""
    print(f">> [RUN] {cmd} (cwd={cwd})")
    res = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    print(res.stdout)
    return res.returncode == 0, res.stdout

def ensure_repo_cloned(repo_slug):
    """
    Given 'owner/name', clone into repos_all/owner__name if not already there.
    Return path to local repo dir.
    """
    owner, name = repo_slug.split("/")
    local_name = f"{owner}__{name}"
    repo_dir = REPO_ROOT / local_name

    if not repo_dir.exists():
        url = f"https://github.com/{repo_slug}.git"
        print(f"Cloning {repo_slug} into {repo_dir} ...")
        ok, _ = run_cmd(f"git clone {url} {repo_dir}", cwd=ROOT)
        if not ok:
            print(f"[ERROR] Failed to clone {repo_slug}")
            return None
    else:
        print(f"Repo {repo_slug} already cloned at {repo_dir}")

    return repo_dir

def reset_to_base(repo_dir, base_commit):
    """Hard reset repo to base commit and wipe untracked files."""
    ok, _ = run_cmd(f"git reset --hard {base_commit}", cwd=repo_dir)
    if not ok:
        return False
    ok, _ = run_cmd("git clean -xdf", cwd=repo_dir)
    return ok

def create_venv_and_install(repo_dir):
    """Create .venv, install repo and pytest deps."""
    venv_dir = repo_dir / ".venv"
    # fresh venv every time for robustness
    if venv_dir.exists():
        ok, _ = run_cmd("rm -rf .venv", cwd=repo_dir)
        if not ok:
            return False

    ok, _ = run_cmd("python3 -m venv .venv", cwd=repo_dir)
    if not ok:
        return False

    # activate venv and install
    activate = "source .venv/bin/activate"
    cmds = [
        f"{activate} && python -m pip install -U pip wheel setuptools",
        f"{activate} && pip install -e .",
        f"{activate} && pip install 'pytest<9' wcag-contrast-ratio || true",
    ]
    for cmd in cmds:
        ok, _ = run_cmd(cmd, cwd=repo_dir)
        if not ok:
            return False
    return True

def run_tests(repo_dir, test_cmd):
    """Run tests inside venv with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1."""
    activate = "source .venv/bin/activate"
    env_prefix = "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1"
    full_cmd = f"{activate} && {env_prefix} {test_cmd}"
    ok, out = run_cmd(full_cmd, cwd=repo_dir)
    return ok, out

def apply_patch(repo_dir, patch_text, label):
    """Apply a unified diff (patch_text) to repo via git apply."""
    if not patch_text:
        print(f"[WARN] No {label} patch text; skipping apply.")
        return True

    # write patch to temp file under repo
    patch_file = repo_dir / f"{label}.patch"
    patch_file.write_text(patch_text)
    cmd = f"git apply --index --reject --whitespace=nowarn {patch_file.name}"
    ok, _ = run_cmd(cmd, cwd=repo_dir)
    if not ok:
        print(f"[ERROR] Failed to apply {label} patch ({patch_file}).")
    return ok

def extract_test_files_from_patch(patch_text):
    """Extract test file paths from a unified diff patch."""
    import re
    if not patch_text:
        return []
    
    test_files = []
    for line in patch_text.split('\n'):
        if line.startswith('diff --git'):
            # Extract file path from: diff --git a/path/to/file.py b/path/to/file.py
            match = re.search(r'b/(.*test.*\.py)', line, re.IGNORECASE)
            if match:
                test_file = match.group(1)
                if test_file not in test_files:
                    test_files.append(test_file)
    
    return test_files

def load_completed_tasks(results_path):
    """Load already-completed tasks from results file to enable resuming."""
    completed = set()
    if results_path.exists():
        print(f"[INFO] Found existing results file: {results_path}")
        try:
            with open(results_path) as f:
                for line in f:
                    if line.strip():
                        result = json.loads(line)
                        key = (result["repo"], result["base_commit"])
                        completed.add(key)
            print(f"[INFO] Found {len(completed)} already-completed tasks. Will skip them.")
        except Exception as e:
            print(f"[WARN] Error reading results file: {e}. Starting fresh.")
    return completed

def main():
    # ----- 1. Load tasks from Oracle dataset -----
    tasks = []
    print(f"Loading tasks from Oracle dataset at {ORACLE_ROOT} ...")
    
    index_csv = ORACLE_ROOT / "index.csv"
    if not index_csv.exists():
        print(f"[ERROR] index.csv not found at {index_csv}")
        return
    
    with open(index_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            repo_folder = Path(row['repo_folder'])
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
                                
                                repo = features.get("repo")
                                base = features.get("base_commit")
                                test_patch = features.get("test_patch", "")
                                fix_patch = features.get("patch", "")
                                
                                if not repo or not base:
                                    print(f"[WARN] Missing repo or base_commit in {oracle_file}")
                                    continue
                                
                                # Extract test files from test_patch
                                test_files = extract_test_files_from_patch(test_patch)
                                
                                # Build test command
                                if test_files:
                                    # Run only the specific test files mentioned in test_patch
                                    test_cmd = f"python -m pytest -xvs {' '.join(test_files)}"
                                else:
                                    # Fallback: try running tests directory
                                    test_cmd = "python -m pytest -xvs tests/"
                                
                                tasks.append({
                                    "repo": repo,
                                    "base": base,
                                    "test_patch": test_patch,
                                    "fix_patch": fix_patch,
                                    "test_cmd": test_cmd,
                                })
                        except Exception as e:
                            print(f"[ERROR] Failed to load {oracle_file}: {e}")
                            continue

    print(f"Found {len(tasks)} tasks from Oracle dataset.")

    # Load already-completed tasks to enable resuming
    completed_tasks = load_completed_tasks(RESULTS_PATH)

    # Filter out completed tasks
    if completed_tasks:
        original_count = len(tasks)
        tasks = [t for t in tasks if (t["repo"], t["base"]) not in completed_tasks]
        skipped = original_count - len(tasks)
        print(f"[INFO] Skipped {skipped} already-completed tasks")
        print(f"[INFO] {len(tasks)} tasks remaining to process")

    # ----- 2. Run PoC for each task -----
    results = []
    repos_processed = set()  # Track unique repos processed
    MAX_REPOS = 300  # Stop after processing this many repos (comment out to run all)
    
    for info in tasks:
        repo_slug = info["repo"]
        base_commit = info["base"]
        print("\n====================================================")
        print(f"Processing {repo_slug} @ {base_commit}")
        print(f"Test command: {info['test_cmd']}")
        print("====================================================")

        repo_dir = ensure_repo_cloned(repo_slug)
        if repo_dir is None:
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": "ERROR",
                "test_patch": "SKIP",
                "fix_patch": "SKIP",
                "note": "clone_failed",
            })
            continue

        # BASELINE
        if not reset_to_base(repo_dir, base_commit):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": "ERROR",
                "test_patch": "SKIP",
                "fix_patch": "SKIP",
                "note": "reset_failed_baseline",
            })
            continue

        if not create_venv_and_install(repo_dir):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": "ERROR",
                "test_patch": "SKIP",
                "fix_patch": "SKIP",
                "note": "venv_install_failed_baseline",
            })
            continue

        base_ok, _ = run_tests(repo_dir, info["test_cmd"])
        base_status = "PASS" if base_ok else "FAIL"

        # TEST PATCH: base + test_patch
        if not reset_to_base(repo_dir, base_commit):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": "ERROR",
                "fix_patch": "SKIP",
                "note": "reset_failed_test_patch",
            })
            continue

        if not apply_patch(repo_dir, info["test_patch"], "test_patch"):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": "ERROR",
                "fix_patch": "SKIP",
                "note": "apply_test_patch_failed",
            })
            continue

        if not create_venv_and_install(repo_dir):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": "ERROR",
                "fix_patch": "SKIP",
                "note": "venv_install_failed_test_patch",
            })
            continue

        test_ok, _ = run_tests(repo_dir, info["test_cmd"])
        test_status = "PASS" if test_ok else "FAIL"

        # FIX PATCH: base + test_patch + fix_patch
        if not reset_to_base(repo_dir, base_commit):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": test_status,
                "fix_patch": "ERROR",
                "note": "reset_failed_fix_patch",
            })
            continue

        if not apply_patch(repo_dir, info["test_patch"], "test_patch"):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": test_status,
                "fix_patch": "ERROR",
                "note": "apply_test_patch_failed_fix_phase",
            })
            continue

        if not apply_patch(repo_dir, info["fix_patch"], "fix_patch"):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": test_status,
                "fix_patch": "ERROR",
                "note": "apply_fix_patch_failed",
            })
            continue

        if not create_venv_and_install(repo_dir):
            results.append({
                "repo": repo_slug,
                "base_commit": base_commit,
                "baseline": base_status,
                "test_patch": test_status,
                "fix_patch": "ERROR",
                "note": "venv_install_failed_fix_patch",
            })
            continue

        fix_ok, _ = run_tests(repo_dir, info["test_cmd"])
        fix_status = "PASS" if fix_ok else "FAIL"

        results.append({
            "repo": repo_slug,
            "base_commit": base_commit,
            "baseline": base_status,
            "test_patch": test_status,
            "fix_patch": fix_status,
            "note": "ok",
        })

        # write incremental result to disk so progress is not lost
        with RESULTS_PATH.open("a") as out_f:
            out_f.write(json.dumps(results[-1]) + "\n")
        
        # Track repos processed and stop after MAX_REPOS (for testing)
        repos_processed.add(repo_slug)
        if len(repos_processed) >= MAX_REPOS:
            print(f"\n[INFO] Stopping after processing {MAX_REPOS} repos (for testing)")
            print(f"[INFO] Processed repos: {', '.join(sorted(repos_processed))}")
            break

    # ----- 3. Print Summary Statistics -----
    print("\n" + "="*60)
    print("=== SUMMARY ===")
    print("="*60)
    
    total = len(results)
    
    # Count baseline results
    baseline_pass = sum(1 for r in results if r['baseline'] == 'PASS')
    baseline_fail = sum(1 for r in results if r['baseline'] == 'FAIL')
    baseline_error = sum(1 for r in results if r['baseline'] == 'ERROR')
    
    # Count test_patch results
    test_pass = sum(1 for r in results if r['test_patch'] == 'PASS')
    test_fail = sum(1 for r in results if r['test_patch'] == 'FAIL')
    test_error = sum(1 for r in results if r['test_patch'] == 'ERROR')
    test_skip = sum(1 for r in results if r['test_patch'] == 'SKIP')
    
    # Count fix_patch results
    fix_pass = sum(1 for r in results if r['fix_patch'] == 'PASS')
    fix_fail = sum(1 for r in results if r['fix_patch'] == 'FAIL')
    fix_error = sum(1 for r in results if r['fix_patch'] == 'ERROR')
    fix_skip = sum(1 for r in results if r['fix_patch'] == 'SKIP')
    
    print(f"\nTotal tasks processed: {total}")
    print(f"\nResults file: {RESULTS_PATH}")
    
    print(f"\n--- Baseline (base commit only) ---")
    print(f"  PASS:  {baseline_pass:3d} ({100*baseline_pass/total if total > 0 else 0:.1f}%)")
    print(f"  FAIL:  {baseline_fail:3d} ({100*baseline_fail/total if total > 0 else 0:.1f}%)")
    print(f"  ERROR: {baseline_error:3d} ({100*baseline_error/total if total > 0 else 0:.1f}%)")
    
    print(f"\n--- Test Patch (base + test_patch) ---")
    print(f"  PASS:  {test_pass:3d} ({100*test_pass/total if total > 0 else 0:.1f}%)")
    print(f"  FAIL:  {test_fail:3d} ({100*test_fail/total if total > 0 else 0:.1f}%)")
    print(f"  ERROR: {test_error:3d} ({100*test_error/total if total > 0 else 0:.1f}%)")
    print(f"  SKIP:  {test_skip:3d} ({100*test_skip/total if total > 0 else 0:.1f}%)")
    
    print(f"\n--- Fix Patch (base + test_patch + fix_patch) ---")
    print(f"  PASS:  {fix_pass:3d} ({100*fix_pass/total if total > 0 else 0:.1f}%)")
    print(f"  FAIL:  {fix_fail:3d} ({100*fix_fail/total if total > 0 else 0:.1f}%)")
    print(f"  ERROR: {fix_error:3d} ({100*fix_error/total if total > 0 else 0:.1f}%)")
    print(f"  SKIP:  {fix_skip:3d} ({100*fix_skip/total if total > 0 else 0:.1f}%)")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()

