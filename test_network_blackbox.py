import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from external_probe import run_probe

ROOT = Path(__file__).parent


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        s = socket.socket()
        try:
            s.connect(("127.0.0.1", port))
            return
        except OSError:
            time.sleep(0.05)
        finally:
            s.close()
    raise RuntimeError("server did not start")


def load_task():
    with open(ROOT / "agent_task_fixture.json", encoding="utf-8") as f:
        return json.load(f)


def with_server(fn):
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        wait_port(port)
        return fn(f"http://127.0.0.1:{port}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_real_http_black_box_happy_path():
    out = with_server(lambda base: run_probe(base, load_task()))
    assert out["ok"] is True
    assert out["network_black_box"] is True
    assert out["recovered_from_422"] is False
    assert out["interpretation"]["execution_authorized"] is False


def test_real_http_black_box_422_self_repair():
    out = with_server(lambda base: run_probe(base, load_task(), inject_error=True))
    assert out["ok"] is True
    assert out["recovered_from_422"] is True
    assert out["trace"].count(["POST", "/inspect"]) == 2
    assert ["GET", "/llms.txt"] in out["trace"]


def test_probe_does_not_import_service_or_engine():
    source = (ROOT / "external_probe.py").read_text(encoding="utf-8")
    assert "tensegrity_control_mesh" not in source
    assert "from app" not in source
    assert "fastapi" not in source.lower()


def test_deploy_files_exist():
    assert (ROOT / "render.yaml").exists()
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "requirements.txt").exists()


def test_render_start_command_binds_public_interface():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "--host 0.0.0.0" in text
    assert "--port $PORT" in text
    assert "healthCheckPath: /capabilities" in text


def test_no_payment_layer_claimed_by_probe():
    out = with_server(lambda base: run_probe(base, load_task()))
    assert out["checks"]["non_authorizing"] is True
