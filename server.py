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
