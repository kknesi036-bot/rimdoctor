"""HTTP smoke check against a running container; no external packages."""
import argparse
import json
import time
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:18000")
parser.add_argument("--version", required=True)
args = parser.parse_args()

def fetch(path, data=None, content_type=None):
    request = Request(args.url + path, data=data, headers={"Content-Type": content_type} if content_type else {})
    with urlopen(request, timeout=5) as response:
        return response.read()

for attempt in range(30):
    try:
        health = json.loads(fetch("/health"))
        break
    except (OSError, ValueError):
        if attempt == 29:
            raise
        time.sleep(1)
assert health["status"] == "ok", health
assert health["version"] == args.version, health
assert "RimDoctor" in fetch("/").decode("utf-8")
for name in ("app.js", "style.css"):
    assert fetch("/static/" + name)
sample = fetch("/static/sample.log")
result = json.loads(fetch("/api/analyze", sample, "text/plain;charset=UTF-8"))
assert result["summary"]["error_count"] == 5, result["summary"]
assert result["summary"]["group_count"] == 4, result["summary"]
assert result["rules_version"] == health["rules_version"]
print(json.dumps({"status":"passed", "version":health["version"], "rules_version":health["rules_version"], "sample":result["summary"]}, ensure_ascii=False))
