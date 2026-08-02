import sys
import os
from pathlib import Path

# Resolve workspace root dynamically
sys.path.append(str(Path(__file__).resolve().parents[1]))

import subprocess

def run_e2e_test():
    print("Running predict command for South Africa vs Canada...")
    # Using python executable from current environment
    cmd = [sys.executable, "main.py", "predict", "South Africa vs Canada"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)
    
    assert result.returncode == 0
    assert "Player Goals" in result.stdout or "Player Assists" in result.stdout or "Player G/A" in result.stdout
    assert "Predict Portfolio Bot Paper Bets" in result.stdout
    print("ALL END-TO-END VERIFICATION CHECKS PASSED!")

if __name__ == "__main__":
    run_e2e_test()
