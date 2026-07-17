"""HTTP API + WebSocket 服务器 —— 让回响成为可嵌入的服务.

零外部依赖（Python 内置 http.server + asyncio）。
可选 FastAPI 模式（pip install fastapi uvicorn）。

端点:
  GET  /status     → Echo 完整状态 JSON
  POST /chat       → 非流式对话
  GET  /stream     → WebSocket 流式对话
  GET  /dashboard  → 简易 HTML 仪表盘
"""

import asyncio
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path


class EchoAPIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 —— 持有 Echo 实例的引用."""

    echo_instance = None  # 类属性，在启动时注入

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _html_response(self, html: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/status":
            if self.echo_instance:
                self._json_response(self.echo_instance.status())
            else:
                self._json_response({"error": "Echo not initialized"}, 503)

        elif parsed.path == "/dashboard":
            self._html_response(DASHBOARD_HTML)

        elif parsed.path == "/health":
            self._json_response({"status": "ok", "time": time.time()})

        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_response({"error": "invalid JSON"}, 400)
            return

        if parsed.path == "/chat":
            if not self.echo_instance:
                self._json_response({"error": "Echo not initialized"}, 503)
                return

            user_input = data.get("message", "")
            if not user_input:
                self._json_response({"error": "missing 'message' field"}, 400)
                return

            response = self.echo_instance.respond(user_input)
            self._json_response(response)

        else:
            self._json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默日志


# ── 简易仪表盘 HTML ──

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>回响 · Echo Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
  h1 { color: #58a6ff; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .card h2 { font-size: 14px; color: #8b949e; margin-bottom: 12px; text-transform: uppercase; }
  .stat { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; }
  .stat .val { color: #58a6ff; font-weight: bold; }
  .bar { height: 6px; background: #21262d; border-radius: 3px; margin: 8px 0; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s; }
  .mood-excited { color: #f0883e; } .mood-calm { color: #58a6ff; } .mood-anxious { color: #f85149; }
  #log { background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 12px;
         height: 300px; overflow-y: auto; font-family: monospace; font-size: 12px; white-space: pre-wrap; }
  button { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
  button:hover { background: #2ea043; }
</style>
</head>
<body>
<h1>🌀 回响 · Echo Dashboard</h1>
<div class="grid">
  <div class="card"><h2>Mood</h2><div id="mood">Loading...</div></div>
  <div class="card"><h2>Memory</h2><div id="memory">Loading...</div></div>
  <div class="card"><h2>Review</h2><div id="review">Loading...</div></div>
  <div class="card"><h2>Module Bus</h2><div id="bus">Loading...</div></div>
</div>
<div class="card" style="margin-top:16px">
  <h2>Live Log</h2>
  <div id="log">Connecting...</div>
  <button onclick="refresh()" style="margin-top:8px">Refresh</button>
</div>
<script>
async function refresh() {
  try {
    const r = await fetch('/status');
    const s = await r.json();
    document.getElementById('mood').innerHTML =
      `Valence: ${s.emotion?.valence?.toFixed(2) || '?'} Arousal: ${s.emotion?.arousal?.toFixed(2) || '?'}<br>` +
      `Mood: ${s.emotion?.mood || '?'} | Interactions: ${s.interaction_count}`;
    document.getElementById('memory').innerHTML =
      `Count: ${s.memory_count} | Principles: ${s.principles_count}<br>` +
      `Anchors: ${s.anchors_formed}/${s.anchors_total} | Crystallized: ${s.crystallized_patterns}`;
    const c = s.critique || {};
    document.getElementById('review').innerHTML =
      `Reviews: ${c.total_reviews || 0} | Pass: ${c.pass_count || 0}<br>` +
      `Revise: ${c.revise_count || 0} | Reject: ${c.reject_count || 0}`;
    const bus = s.bus_modules || [];
    document.getElementById('bus').innerHTML = bus.map(m =>
      `${m.enabled ? '✅' : '❌'} ${m.name} (${m.category})`).join('<br>');
    const log = document.getElementById('log');
    log.textContent = JSON.stringify(s, null, 2);
  } catch(e) { console.error(e); }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


def run_server(echo_instance, host: str = "127.0.0.1", port: int = 8081):
    """启动 HTTP API 服务器."""
    EchoAPIHandler.echo_instance = echo_instance
    server = HTTPServer((host, port), EchoAPIHandler)
    print(f"🌀 回响 API 服务器已启动: http://{host}:{port}")
    print(f"   仪表盘: http://{host}:{port}/dashboard")
    print(f"   状态:   http://{host}:{port}/status")
    print(f"   Chat:   POST http://{host}:{port}/chat")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        server.shutdown()
