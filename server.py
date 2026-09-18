import os
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import database
from service import RentalScannerService

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health", "/status"]:
            stats = database.get_stats()
            response_data = {
                "status": "running",
                "service": "Timisoara Rent Scanner Bot",
                "version": "1.2.0",
                "stats": stats
            }
            body = json.dumps(response_data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ["/diag"]:
            results = {}
            from scrapers import ImobiliareScraper, StoriaScraper, Publi24Scraper, OLXScraper
            import config
            for cls, name in [(ImobiliareScraper, "imobiliare"), (StoriaScraper, "storia"), (Publi24Scraper, "publi24"), (OLXScraper, "olx")]:
                try:
                    s = cls(config.SOURCES_CONFIG[name]["url"])
                    items = s.fetch_listings()
                    results[name] = {"count": len(items), "status": "ok"}
                except Exception as e:
                    results[name] = {"count": 0, "status": f"error: {e}"}
            body = json.dumps(results, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress noisy HTTP access logs
        return

def run_http_server(port: int):
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"[HTTP] Health check server listening on 0.0.0.0:{port}")
    httpd.serve_forever()

def main():
    database.init_db()
    
    # 1. Start continuous scanner service in background thread
    scanner = RentalScannerService()
    scanner_thread = threading.Thread(target=scanner.start_loop, daemon=True, name="ScannerThread")
    scanner_thread.start()

    # 2. Start HTTP server on main thread (binding to PORT environment variable for cloud hosts)
    port = int(os.getenv("PORT", "8080"))
    run_http_server(port)

if __name__ == "__main__":
    main()

