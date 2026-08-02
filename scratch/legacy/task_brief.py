import sys
import re
import os

def main():
    if len(sys.argv) < 3:
        print("usage: task_brief.py PLAN_FILE TASK_NUMBER [OUTFILE]")
        sys.exit(2)
        
    plan_file = sys.argv[1]
    task_num = sys.argv[2]
    
    if len(sys.argv) == 4:
        outfile = sys.argv[3]
    else:
        outfile = f"C:\\Users\\Bikash\\Desktop\\CODEBASE\\WorldCupPredictor\\.superpowers\\sdd\\task-{task_num}-brief.md"
        
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    
    with open(plan_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    in_fence = False
    in_task = False
    task_lines = []
    
    # Match headings like "### Task N: ..." or "## Task N:"
    pattern = re.compile(rf"^#+\s+Task\s+{task_num}(\b|$)")
    next_task_pattern = re.compile(r"^#+\s+Task\s+(\d+)(\b|$)")
    
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            
        if not in_fence:
            if pattern.search(line):
                in_task = True
            elif in_task and next_task_pattern.search(line):
                break
                
        if in_task:
            task_lines.append(line)
            
    if not task_lines:
        print(f"task {task_num} not found in {plan_file}")
        sys.exit(3)
        
    with open(outfile, "w", encoding="utf-8") as f:
        f.writelines(task_lines)
        
    print(f"wrote {outfile}: {len(task_lines)} lines")

if __name__ == "__main__":
    main()
