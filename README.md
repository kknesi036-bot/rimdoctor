# HW3 1단계: Docker 이미지와 CI

기존 림닥터의 기능은 유지합니다. 로그 자동 입력과 CD/무중단 배포는 이후 단계입니다.

## 추가 파일
- Dockerfile: Python 3.13 기반 이미지, 분석기 로딩 확인, 테스트 단계와 실행 단계 분리
- constraints.txt: 검증한 라이브러리 버전 고정
- .dockerignore: 소스와 필요한 설정만 빌드에 포함
- .github/workflows/ci.yml: main push → 테스트 → 이미지 빌드 → HTTP 분석 확인 → Docker Hub 업로드
- scripts/smoke.py: 실행된 컨테이너의 상태·버전·화면·분석 결과 확인

## Docker 실행
```powershell
docker build --target test --build-arg APP_VERSION=local -t rimdoctor:tests .
docker build --target final --build-arg APP_VERSION=local -t rimdoctor:local .
docker run --rm --name rimdoctor-local -p 127.0.0.1:8000:8000 rimdoctor:local
```
브라우저에서 http://127.0.0.1:8000 을 엽니다. 기존 서버가 8000번을 사용하면 `127.0.0.1:18000:8000`으로 바꾸고 18000번 주소로 접속합니다.

## GitHub 업로드
이 폴더는 기존 `kknesi036-bot/rimdoctor` 저장소에서 복제한 Git 저장소입니다. 파일은 아직 원격에 게시하지 않았습니다.

GitHub 웹 업로드 시 **추가 파일만** 올리려면 별도 변경파일 ZIP을 사용합니다. ZIP 자체가 아니라 압축을 푼 내용물을 저장소 루트에 올립니다. `.github/workflows/ci.yml` 경로가 유지되어야 합니다. 토큰은 파일에 넣지 않습니다.

Git 사용 시 이 폴더에서:
```powershell
git add Dockerfile .dockerignore .gitignore constraints.txt .github/workflows/ci.yml scripts/smoke.py README.md
git commit -m "Add Docker image and CI for RimDoctor"
git push origin main
```

## 인증과 게시 위치
Repository secrets의 `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`을 사용합니다. 사용자명은 `qwer09872234`, 토큰은 이미지 업로드 권한이 필요합니다.

이미지 목적지: `qwer09872234/rimdoctor`. 테스트한 동일 이미지를 커밋 SHA 태그와 `latest` 태그로 게시합니다. Pull request는 테스트·빌드만 수행하고 이미지를 게시하지 않습니다.

main에 push한 뒤 GitHub Actions의 `RimDoctor - Test, Build and Push` 결과와 Docker Hub Tags를 확인합니다. 이 CI는 로컬 서버를 자동 갱신하는 CD까지 구현한 것은 아닙니다.

구성 참고: https://docs.docker.com/build/ci/github-actions/

---

## 기존 HW2 설명 (과거 제출 범위)

# RimDoctor

림월드 로그의 반복 오류와 원문 근거를 정리하는 한국어 웹서비스입니다. Python FastAPI와 HTML/CSS/JavaScript로 구성하며 외부 AI API나 데이터베이스를 사용하지 않습니다.

## 실행

Python 3.13 기준입니다. 프로젝트 폴더에서 실행하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

브라우저에서 http://127.0.0.1:8000 에 접속합니다. 종료는 Ctrl+C입니다. 프로그램 실행만 필요하면 `requirements.txt`를 설치해도 됩니다.

## 사용

파일 업로드 또는 붙여넣기 중 하나를 입력하고 ‘로그 분석’을 누릅니다. ‘샘플로 체험’은 합성 로그 19줄을 분석하며 오류 5회, 그룹 4개가 예상됩니다. ‘원문 근거 보기’에서 줄 번호를 확인할 수 있습니다.

10MiB까지의 `.log` / `.txt`, UTF-8(선택적 BOM)과 BOM이 있는 UTF-16을 지원합니다. 파일은 메모리에서 처리하며 임시 파일·사용자 원문·분석 결과를 저장하지 않습니다. 브라우저의 입력과 결과는 초기화 버튼 또는 새로고침으로 지울 수 있습니다. 로컬 주소로 실행하므로 외부 호스팅 계정이 필요하지 않습니다.

## 진단 범위와 한계

- 참조 오류, XML 로딩/패치 오류, 타입·어셈블리 로딩 오류를 규칙으로 분류합니다.
- 오류 헤더와 뒤따르는 들여쓴 줄/호출 기록을 묶습니다. 게임 버전과 모드별 모든 로그 형식을 보장하지 않습니다.
- 타임스탬프만 정규화합니다. 다른 수치·경로·객체 ID·호출 기록은 다른 오류 그룹이 될 수 있습니다.
- `[mod: 이름]` 같은 명시적 표기만 모드 후보로 추출합니다. 일반 로그의 네임스페이스를 모드 이름으로 추정하지 않습니다. 표기가 없으면 후보가 없을 수 있습니다.
- 같은 오류의 여러 회 발생은 게임 원인의 수와 같지 않습니다. Unity/게임 자체의 중복 생략 로그는 원래 발생 횟수를 복원하지 않습니다.
- 합성 샘플과 사용자 로컬 로그 1개로 검증했습니다. 전 버전 호환성을 보장하지 않습니다. 로딩 참고 기록과 저장 데이터 참조 경고는 오류 횟수에서 제외합니다.
- 원인 확정, 모드 자동 변경, 게임 정상 여부 판정 도구가 아닙니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## API

- `GET /health`: `status`, `version`, `rules_version`.
- `POST /api/analyze`: `text/plain` 원문 또는 `application/octet-stream` 파일 바이트. 파일은 URL 인코딩한 `X-File-Name` 헤더를 함께 보냅니다. multipart/JSON은 받지 않습니다. 업로드의 디스크 임시 저장을 피하기 위한 방식입니다.
- 결과: `summary`(line_count/error_count/group_count), `groups`(rule_id/title/count/explanation/next_steps/related_mod_candidates/occurrences), `rules_version`, `notice`.
- 발생 구간은 1부터 시작하는 `start_line`, `end_line`, `raw`를 포함합니다. 입력 오류는 `{"error":"한국어 안내"}`와 400/413/415 상태를 반환합니다.

## 과제 범위와 DevOps 연계

설명 영상 07:15~07:44에서는 외부 서비스 배포를 로컬 FastAPI 실행 화면으로 대체한다고 안내합니다. 이번 구현 범위는 프로그램 개발, GitHub 소스 업로드, 로컬 정상 작동 증빙입니다.

Git으로 변경 이력을 관리하고, 의존성 목록과 실행 절차를 공개해 다른 환경에서 재현할 수 있도록 했습니다. 분석 규칙별 회귀 테스트를 제공하므로 추후 자동 테스트와 배포 파이프라인에 연결할 수 있습니다. 외부 서버 구축과 자동 배포를 구현했다고 주장하지 않습니다.

## GitHub 업로드

이 폴더의 소스만 프로젝트 저장소에 올립니다. 브라우저 증빙과 보고서는 별도의 제출물로 관리합니다. 소스에는 인증정보, 실제 사용자 로그, 학번·이름을 넣지 않습니다.

공개 대상: `app/`, `tests/`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `README.md`.
제외 대상: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, 개인 로그와 테스트 입력 파일.

## 제출 증빙

1. GitHub 저장소에 소스가 올라간 화면.
2. 로컬 프로그램에서 샘플 또는 로그를 분석한 결과 화면.
3. 목적, 개발 방법, 기능, 검증 및 한계를 설명하는 1페이지 보고서.
