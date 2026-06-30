import sys
import re
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python task_brief.py PLAN_FILE TASK_NUMBER [OUTFILE]")
        sys.exit(2)
    plan_file = sys.argv[1]
    task_num = sys.argv[2]
    
    if not os.path.exists(plan_file):
        print(f"no such plan file: {plan_file}")
        sys.exit(2)
        
    if len(sys.argv) == 4:
        outfile = sys.argv[3]
    else:
        # Resolve using git
        import subprocess
        root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
        sdd_dir = os.path.join(root, ".superpowers", "sdd")
        os.makedirs(sdd_dir, exist_ok=True)
        with open(os.path.join(sdd_dir, ".gitignore"), "w") as f:
            f.write("*\n")
        outfile = os.path.join(sdd_dir, f"task-{task_num}-brief.md")
        
    # Read plan
    with open(plan_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Find heading matching "### Task N:" or similar
    pattern = rf"(^### Task {task_num}\b.*?)(?=^### Task \d+\b|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        # Fall back to standard headers
        pattern = rf"(^#+\s+Task\s+{task_num}\b.*?)(?=^#+\s+Task\s+\d+\b|\Z)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        print(f"task {task_num} not found in {plan_file}")
        sys.exit(3)
        
    task_text = match.group(1).strip()
    
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(task_text + "\n")
        
    print(f"wrote {outfile}: {len(task_text.splitlines())} lines")

if __name__ == "__main__":
    main()
