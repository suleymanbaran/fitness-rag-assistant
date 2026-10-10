"""HTTPS front for the local API, so Google can redirect back to this machine.

Google's OAuth setup form rejects http:// URIs, including localhost. This serves
https://localhost:8443 and forwards every request to the API on port 8000.
The certificate is self-signed; the browser will ask you to continue once.
"""

import socket
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

UPSTREAM = "http://127.0.0.1:8000"
CERTS = Path(__file__).resolve().parent.parent / ".certs"
PORT = 8443


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length"}}
        try:
            response = httpx.request(
                self.command,
                f"{UPSTREAM}{self.path}",
                content=body,
                headers=headers,
                follow_redirects=False,
                timeout=60,
            )
        except httpx.HTTPError as exc:
            payload = f"API unreachable at {UPSTREAM}: {exc}".encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(response.status_code)
        for key, value in response.headers.items():
            if key.lower() in {"transfer-encoding", "content-encoding", "content-length", "connection"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[https] {self.address_string()} {fmt % args}")


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main() -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERTS / "localhost.pem", CERTS / "localhost-key.pem")
    server = DualStackServer(("::", PORT), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"https://localhost:{PORT} -> {UPSTREAM}")
    server.serve_forever()


if __name__ == "__main__":
    main()
