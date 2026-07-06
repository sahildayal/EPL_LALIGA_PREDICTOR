import http.server
import socketserver
import json
import subprocess
import os
import sys

PORT = 8080

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence access logging to keep terminal clean
        pass

    def do_GET(self):
        if self.path == '/api/debates':
            try:
                debates_dir = os.path.join("data", "processed", "debates")
                active_debates = []
                if os.path.exists(debates_dir):
                    for f in os.listdir(debates_dir):
                        if f.endswith(".json"):
                            parts = f[:-5].split("-")
                            if len(parts) >= 4:
                                date_str = "-".join(parts[:3])
                                if "vs" in parts:
                                    vs_idx = parts.index("vs")
                                    home_clean = "_".join(parts[3:vs_idx]).replace("_", " ")
                                    away_clean = "_".join(parts[vs_idx+1:]).replace("_", " ")
                                    active_debates.append({
                                        "filename": f,
                                        "date": date_str,
                                        "home": home_clean,
                                        "away": away_clean
                                    })
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(active_debates).encode('utf-8'))
            except Exception as e:
                self.send_error_response(str(e))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/run':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                command = data.get('command')
                query = data.get('query', '')
                
                if command not in ['predict', 'ask', 'parlay']:
                    self.send_error_response("Invalid command")
                    return
                
                # Build command args
                args = [sys.executable, 'main.py', command]
                if command == 'parlay':
                    args.append('--today')
                    if data.get('longshot', False):
                        args.append('--longshot')
                else:
                    args.append(query)
                
                print(f"[SERVER] Executing subprocess: {' '.join(args)}")
                
                # Execute subprocess
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                output = result.stdout + "\n" + result.stderr
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                response = {
                    "success": result.returncode == 0,
                    "output": output
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            except Exception as e:
                self.send_error_response(str(e))
        else:
            self.send_error_response("Not Found", code=404)
            
    def send_error_response(self, message, code=400):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "error": message}).encode('utf-8'))

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"[SERVER] Running World Cup Predictor server at http://localhost:{PORT}")
        # Automatically launch web browser
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}/dashboard.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")

if __name__ == '__main__':
    main()
