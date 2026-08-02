import os
import subprocess
import time
import json
import secrets

def main():
    project_dir = r"C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor"
    session_dir = os.path.join(project_dir, ".superpowers", "brainstorm", "session")
    content_dir = os.path.join(session_dir, "content")
    state_dir = os.path.join(session_dir, "state")
    
    os.makedirs(content_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    
    server_id = secrets.token_hex(24)
    server_cjs = r"C:\Users\Bikash\.gemini\config\plugins\superpowers\skills\brainstorming\scripts\server.cjs"
    log_path = os.path.join(state_dir, "server.log")
    
    # Clean up old PID file if exists
    pid_file = os.path.join(state_dir, "server.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            # Kill process if active
            import signal
            os.kill(old_pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            os.remove(pid_file)
        except Exception:
            pass
            
    # Set environment variables
    env = os.environ.copy()
    env["BRAINSTORM_DIR"] = session_dir
    env["BRAINSTORM_HOST"] = "0.0.0.0"
    env["BRAINSTORM_URL_HOST"] = "localhost"
    env["BRAINSTORM_OWNER_PID"] = ""
    env["BRAINSTORM_OPEN"] = "1"
    
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        ["node", server_cjs, f"--brainstorm-server-id={server_id}"],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT
    )
    
    # Save PID
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))
        
    print(f"Spawned server with PID {proc.pid}")
    
    # Wait for server-started message in the log
    for _ in range(50):
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                content = f.read()
            if "server-started" in content:
                for line in content.splitlines():
                    if "server-started" in line:
                        print(line)
                        return
        time.sleep(0.1)
        
    print(f"Timeout: Server failed to output server-started in {log_path}")

if __name__ == "__main__":
    main()
