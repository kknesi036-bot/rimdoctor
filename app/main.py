import os
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .analyzer import RULES_VERSION, analyze

MAX_BYTES = 10 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
VERSION = os.getenv("APP_VERSION", "1.0.0")
app = FastAPI(title="RimDoctor", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION, "rules_version": RULES_VERSION}


def error(message, status=400):
    return JSONResponse({"error": message}, status_code=status)


@app.post("/api/analyze")
async def analyze_log(request: Request):
    """Raw UTF-8 text or file bytes, not multipart; never spools uploads to disk."""
    media = request.headers.get("content-type", "").split(";")[0]
    if media not in {"text/plain", "application/octet-stream"}:
        return error("텍스트 또는 로그 파일을 입력해 주세요.", 415)
    if media == "application/octet-stream":
        filename = unquote(request.headers.get("x-file-name", ""))
        if Path(filename).suffix.lower() not in {".log", ".txt"}:
            return error(".log 또는 .txt 파일만 분석할 수 있습니다.")
    declared = request.headers.get("content-length")
    if declared and (not declared.isdigit() or int(declared) > MAX_BYTES):
        return error("입력은 최대 10MB까지 가능합니다.", 413)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BYTES:
            return error("입력은 최대 10MB까지 가능합니다.", 413)
        data.extend(chunk)
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig")
    except UnicodeError:
        return error("파일을 읽을 수 없습니다. UTF-8 또는 BOM이 있는 UTF-16 텍스트로 저장해 주세요.")
    if not text.strip():
        return error("로그 파일을 선택하거나 내용을 붙여넣어 주세요.")
    if any(ord(c) < 32 and c not in "\r\n\t" for c in text):
        return error("텍스트 로그가 아닌 파일입니다. .log 또는 .txt 파일을 확인해 주세요.")
    return await run_in_threadpool(analyze, text)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
