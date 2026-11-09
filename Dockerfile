FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY constraints.txt requirements.txt ./
RUN python -m pip install --no-cache-dir -c constraints.txt -r requirements.txt && python -m pip check
COPY app ./app
# Verify the existing rules and bundled synthetic sample while building.
RUN python -c "from pathlib import Path; from app.analyzer import analyze; from app.main import app; r=analyze(Path('app/static/sample.log').read_text(encoding='utf-8')); assert r['summary']['error_count']==5; assert r['summary']['group_count']==4"
RUN useradd --create-home --uid 10001 rimdoctor
ARG APP_VERSION=local
ENV APP_VERSION=$APP_VERSION
USER rimdoctor
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test
USER root
COPY requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -c constraints.txt -r requirements-dev.txt && python -m pip check
COPY tests ./tests
USER rimdoctor
RUN python -m pytest -q -p no:cacheprovider

FROM runtime AS final
