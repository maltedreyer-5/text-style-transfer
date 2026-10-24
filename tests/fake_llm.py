# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""A minimal OpenAI-compatible chat-completions server for tests.

Behaviour is selected per server through `mode`:
- "ok":        returns the user text in upper case; for the neutralisation
               step the text unchanged after a reasoning block; a JSON
               profile or JSON rules when the system prompt asks for JSON
- "status500": always HTTP 500
- "status400": always HTTP 400
- "empty":     empty content, finish_reason "stop"
- "length":    empty content, finish_reason "length"
- "reasoning": only an unterminated <think> block
"""

from __future__ import annotations

import http.server
import json
import threading

PROFILE_JSON = {
    "sliders": {"formal": 7, "funny": 4, "not_a_slider": 3, "cefr_level": "B2"},
    "description": "Short sentences, warm tone.",
    "rules": ["Use short sentences.", "Address the reader directly."],
}


class FakeLLM:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.requests: list[dict] = []
        handler = self._handler()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __enter__(self) -> FakeLLM:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):  # type: ignore[no-untyped-def]
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send(self, status: int, body: dict) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:  # noqa: N802 - required name
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fake.requests.append(body)
                if fake.mode == "status500":
                    return self._send(500, {"error": {"message": "boom"}})
                if fake.mode == "status400":
                    return self._send(400, {"error": {"message": "bad"}})
                system = body["messages"][0]["content"]
                user = body["messages"][1]["content"]
                finish, content = "stop", user.upper()
                if fake.mode == "empty":
                    content = ""
                elif fake.mode == "length":
                    content, finish = "", "length"
                elif fake.mode == "reasoning":
                    content = "<think>still thinking about it"
                elif "rules" in system and "Respond with one JSON object" in system:
                    content = json.dumps(PROFILE_JSON) if "sliders" in system else json.dumps({"rules": ["Prefer active verbs."]})
                elif "neutralise" in system:
                    content = "<think>plan</think>" + user
                return self._send(200, {
                    "id": "x", "object": "chat.completion", "created": 0, "model": body.get("model"),
                    "choices": [{"index": 0, "finish_reason": finish,
                                 "message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                })

        return Handler
