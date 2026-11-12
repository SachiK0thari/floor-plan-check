"""Local jurisdiction review and exact-input check server. Run python -m plancheck.web."""

from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from plancheck.jurisdiction.proposal import propose
from plancheck.jurisdiction.resolve import load_adoption_records
from plancheck.local_projects import DOWNLOADS, LocalProjects, SaveRequest

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "out" / "projects"


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=200)
    data: str


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    revision: int = Field(ge=1)


class LocalServer(HTTPServer):
    def server_bind(self) -> None:
        # Loopback-only service: avoid reverse DNS during local startup.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def reply(self, value: object, status: int = 200) -> None:
        data = json.dumps(value).encode()
        if status == 200:
            self.send_bytes(data, "application/json")
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def local_request(self) -> bool:
        host = self.headers.get("Host", "")
        if urlsplit("//" + host).hostname not in {"127.0.0.1", "localhost"}:
            self.reply({"error": "Use the localhost address for this local service."}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            self.reply({"error": "Cross-origin request rejected"}, 403)
            return False
        return True

    def do_GET(self) -> None:
        if not self.local_request():
            return
        projects = LocalProjects(STORE)
        try:
            if self.path == "/":
                self.send_bytes(
                    (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8"
                )
            elif self.path == "/app.js":
                self.send_bytes(
                    (ROOT / "web" / "app.js").read_bytes(), "text/javascript; charset=utf-8"
                )
            elif self.path == "/api/projects":
                self.reply([p.model_dump(mode="json") for p in projects.list()])
            elif self.path == "/api/authorities":
                self.reply([r.model_dump(mode="json") for r in load_adoption_records()])
            elif self.path.startswith("/api/download/"):
                parts = self.path.split("/")
                if len(parts) != 6:
                    raise ValueError("Invalid download path")
                project_id, run_id, filename = UUID(parts[3]), UUID(parts[4]), parts[5]
                path = projects.download(project_id, run_id, filename)
                self.send_bytes(path.read_bytes(), DOWNLOADS[filename], filename)
            else:
                self.reply({"error": "Not found"}, 404)
        except FileNotFoundError:
            self.reply({"error": "Saved project or output not found."}, 404)
        except ValueError as error:
            self.reply({"error": str(error)}, 400)

    def do_POST(self) -> None:
        if not self.local_request():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 20_000_000:
                raise ValueError("Request must be between 1 byte and 20 MB")
            body = json.loads(self.rfile.read(length))
            projects = LocalProjects(STORE)
            if self.path == "/api/extract":
                request = UploadRequest.model_validate(body)
                drawing = projects.upload(
                    request.name, base64.b64decode(request.data, validate=True)
                )
                self.reply(
                    {
                        "upload_id": drawing.id,
                        "extraction": drawing.evidence.model_dump(mode="json"),
                        "proposal": propose(drawing.evidence, load_adoption_records()).model_dump(
                            mode="json"
                        ),
                    }
                )
            elif self.path == "/api/save":
                project = projects.save(SaveRequest.model_validate(body))
                self.reply(project.model_dump(mode="json"))
            elif self.path == "/api/run":
                request_run = RunRequest.model_validate(body)
                project = projects.run(request_run.id, request_run.revision)
                self.reply(project.model_dump(mode="json"))
            else:
                self.reply({"error": "Not found"}, 404)
        except FileNotFoundError:
            self.reply({"error": "Saved project or drawing not found. Upload and save again."}, 404)
        except Exception as error:
            self.reply({"error": str(error)}, 400)


def main() -> None:
    print("PlanCheck local review: http://127.0.0.1:8000", flush=True)
    LocalServer(("127.0.0.1", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
