import sys
import subprocess
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python review_package.py BASE HEAD [OUTFILE]")
        sys.exit(2)
    base = sys.argv[1]
    head = sys.argv[2]
    
    # Verify refs
    try:
        subprocess.check_call(["git", "rev-parse", "--verify", "--quiet", base], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"bad BASE: {base}")
        sys.exit(2)
        
    try:
        subprocess.check_call(["git", "rev-parse", "--verify", "--quiet", head], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"bad HEAD: {head}")
        sys.exit(2)
        
    if len(sys.argv) == 4:
        outfile = sys.argv[3]
    else:
        root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip()
        sdd_dir = os.path.join(root, ".superpowers", "sdd")
        os.makedirs(sdd_dir, exist_ok=True)
        base_short = subprocess.check_output(["git", "rev-parse", "--short", base]).decode().strip()
        head_short = subprocess.check_output(["git", "rev-parse", "--short", head]).decode().strip()
        outfile = os.path.join(sdd_dir, f"review-{base_short}..{head_short}.diff")
        
    # Build content
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(f"# Review package: {base}..{head}\n\n")
        f.write("## Commits\n")
        commits_log = subprocess.check_output(["git", "log", "--oneline", f"{base}..{head}"]).decode(errors="replace")
        f.write(commits_log + "\n")
        f.write("## Files changed\n")
        diff_stat = subprocess.check_output(["git", "diff", "--stat", f"{base}..{head}"]).decode(errors="replace")
        f.write(diff_stat + "\n")
        f.write("## Diff\n")
        diff_full = subprocess.check_output(["git", "diff", "-U10", f"{base}..{head}"]).decode(errors="replace")
        f.write(diff_full + "\n")
        
    commits_count = subprocess.check_output(["git", "rev-list", "--count", f"{base}..{head}"]).decode().strip()
    size_bytes = os.path.getsize(outfile)
    print(f"wrote {outfile}: {commits_count} commit(s), {size_bytes} bytes")

if __name__ == "__main__":
    main()
