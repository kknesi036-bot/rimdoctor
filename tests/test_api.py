import pytest
from fastapi.testclient import TestClient

from app.main import MAX_BYTES, app

client = TestClient(app)


def test_health_and_home():
    assert client.get("/health").json()["status"] == "ok"
    response = client.get("/")
    assert response.status_code == 200
    assert "RimDoctor" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_text():
    r = client.post("/api/analyze", content="Error: 테스트", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    assert r.json()["summary"]["error_count"] == 1


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_file_encoding(encoding):
    r = client.post("/api/analyze", content="Error: 한글".encode(encoding), headers={"Content-Type": "application/octet-stream", "X-File-Name": "Player.log"})
    assert r.status_code == 200
    assert "한글" in r.json()["groups"][0]["preview"]


@pytest.mark.parametrize("content,status", [(b"", 400), (b"  \n", 400), (b"\x00\x01", 400), (b"\xff\x00", 400), (b"a" * (MAX_BYTES + 1), 413)])
def test_invalid_inputs(content, status):
    r = client.post("/api/analyze", content=content, headers={"Content-Type": "text/plain"})
    assert r.status_code == status
    assert "error" in r.json()


def test_file_extension():
    r = client.post("/api/analyze", content=b"Error: x", headers={"Content-Type":"application/octet-stream", "X-File-Name":"image.png"})
    assert r.status_code == 400


def test_multipart_and_json_rejected_without_echoing_input():
    r = client.post("/api/analyze", json={"log":"private contents"})
    assert r.status_code == 415
    assert "private contents" not in r.text


def test_streamed_size_limit_without_content_length():
    def chunks():
        for _ in range(11):
            yield b"a" * 1024 * 1024
    r = client.post("/api/analyze", content=chunks(), headers={"Content-Type":"text/plain"})
    assert r.status_code == 413


def test_exact_size_limit():
    r = client.post("/api/analyze", content=b"a" * MAX_BYTES, headers={"Content-Type":"text/plain"})
    assert r.status_code == 200


def test_script_is_text_data():
    raw = 'Error: <script>window.attacked=true</script>'
    r = client.post("/api/analyze", content=raw, headers={"Content-Type":"text/plain"})
    assert r.json()["groups"][0]["occurrences"][0]["raw"] == raw
