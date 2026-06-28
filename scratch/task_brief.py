import sys
import re
from pathlib import Path

def extract_brief(plan_path, task_num, out_path):
    plan_content = Path(plan_path).read_text(encoding='utf-8')
    pattern = rf"(### Task {task_num}:.*?)(?=### Task \d+:|$)"
    match = re.search(pattern, plan_content, re.DOTALL)
    if not match:
        print(f"Task {task_num} not found")
        sys.exit(1)
    brief = match.group(1).strip()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(brief, encoding='utf-8')
    print(f"Wrote brief to {out_path}")

if __name__ == "__main__":
    extract_brief(sys.argv[1], sys.argv[2], sys.argv[3])
