import sys
import subprocess
from pathlib import Path

def run_git(args):
    res = subprocess.run(["git"] + args, capture_output=True, text=True, check=True)
    return res.stdout

def create_review_package(base, head, out_path=None):
    base_short = run_git(["rev-parse", "--short", base]).strip()
    head_short = run_git(["rev-parse", "--short", head]).strip()
    
    if not out_path:
        out_path = Path(".superpowers/sdd") / f"review-{base_short}..{head_short}.diff"
    else:
        out_path = Path(out_path)
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    commits_log = run_git(["log", "--oneline", f"{base}..{head}"])
    diff_stat = run_git(["diff", "--stat", f"{base}..{head}"])
    diff_content = run_git(["diff", "-U10", f"{base}..{head}"])
    
    content = []
    content.append(f"# Review package: {base}..{head}\n")
    content.append("## Commits\n")
    content.append(commits_log + "\n")
    content.append("## Files changed\n")
    content.append(diff_stat + "\n")
    content.append("## Diff\n")
    content.append(diff_content + "\n")
    
    out_path.write_text("".join(content), encoding="utf-8")
    print(f"Wrote review package to {out_path}")

if __name__ == "__main__":
    base = sys.argv[1]
    head = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    create_review_package(base, head, out_path)
