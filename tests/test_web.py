import json
import threading
import urllib.error
import urllib.request

from conftest import make_sample_status
from rover_status.web import StatusHTTPServer, make_handler


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.headers.get("Content-Type"), r.read().decode()


def test_dashboard_endpoints():
    server = StatusHTTPServer(
        ("127.0.0.1", 0), make_handler(make_sample_status))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        code, ctype, body = _get(port, "/status")
        assert code == 200
        assert "application/json" in ctype
        data = json.loads(body)
        assert data["position"]["fix_name"] == "RTK fixed"

        code, ctype, body = _get(port, "/text")
        assert code == 200
        assert "text/plain" in ctype
        assert "fix=4(RTK fixed)" in body

        code, ctype, body = _get(port, "/")
        assert code == 200
        assert "text/html" in ctype
        assert "Rover Status" in body
        assert "__INITIAL_STATUS__" not in body
        assert "RTK fixed" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_unknown_route():
    server = StatusHTTPServer(
        ("127.0.0.1", 0), make_handler(make_sample_status))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        try:
            _get(port, "/nope")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("expected 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
