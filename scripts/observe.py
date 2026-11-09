"""Measure the published endpoint throughout deployment, including an in-flight POST."""
import argparse
import collections
import http.client
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

p = argparse.ArgumentParser()
p.add_argument('--url', default='http://host.docker.internal:8000')
p.add_argument('--expected', required=True)
p.add_argument('--output', default='/proof')
a = p.parse_args()
out = Path(a.output)
out.mkdir(parents=True, exist_ok=True)
started = time.time()
lock = threading.Lock()
records = []
changed = threading.Event()
stop = threading.Event()
slow_ready = threading.Event()
with urlopen(a.url + '/health', timeout=5) as r:
    initial_backend = r.headers.get('X-RimDoctor-Backend')
    initial = json.load(r)['version']

def record(kind, start, ok, **extra):
    item = dict(kind=kind, start=start, end=time.time(), ok=ok, **extra)
    with lock:
        records.append(item)
        with (out / 'requests.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(item) + '\n')

def loop(kind):
    while not stop.is_set():
        start = time.time()
        try:
            path = {'health':'/health', 'home':'/', 'analysis':'/api/analyze'}[kind]
            data = b'Error: deployment probe' if kind == 'analysis' else None
            req = Request(a.url + path, data=data, headers={'Content-Type':'text/plain'})
            with urlopen(req, timeout=5) as r:
                backend = r.headers.get('X-RimDoctor-Backend')
                body = r.read()
                if r.status != 200: raise ValueError(str(r.status))
            extra = {}
            if kind == 'health':
                result = json.loads(body)
                assert result['status'] == 'ok'
                extra['version'] = result['version']
                extra['backend'] = backend
                if result['version'] == a.expected and backend and backend != initial_backend: changed.set()
            elif kind == 'analysis':
                assert json.loads(body)['summary']['error_count'] == 1
            else: assert b'RimDoctor' in body
            record(kind, start, True, **extra)
        except Exception as e: record(kind, start, False, error=str(e))
        stop.wait(0.05)

def in_flight():
    start = time.time()
    conn = None
    try:
        target = urlsplit(a.url)
        conn = http.client.HTTPConnection(target.hostname, target.port, timeout=90)
        body = b'Error: slow upload spanning deployment\n'
        conn.putrequest('POST', '/api/analyze')
        conn.putheader('Content-Type', 'text/plain')
        conn.putheader('Content-Length', str(len(body)))
        conn.endheaders()
        conn.send(body[:10])
        # Let Nginx accept this request before allowing the deployment to start.
        time.sleep(0.5)
        slow_ready.set()
        deadline = time.time() + 90
        while not changed.wait(0.1):
            if stop.is_set() or time.time() > deadline: raise TimeoutError('Deployment ended without a backend switch')
        conn.send(body[10:])
        response = conn.getresponse()
        result = json.loads(response.read())
        assert response.status == 200 and result['summary']['error_count'] == 1
        record('in_flight', start, True, spans_switch=True)
    except Exception as e:
        record('in_flight', start, False, error=str(e))
        slow_ready.set()
    finally:
        if conn: conn.close()

threads = [threading.Thread(target=loop, args=(k,)) for k in ('health','home','analysis')]
threads.append(threading.Thread(target=in_flight))
for t in threads: t.start()
slow_ready.wait(10)
(out / 'ready.json').write_text(json.dumps({'initial':initial}), encoding='utf-8')
while time.time() - started < 240 and not (out / 'stop').exists(): time.sleep(0.2)
stop.set()
for t in threads: t.join()
latencies = sorted((r['end'] - r['start']) * 1000 for r in records if r['kind'] != 'in_flight')
failures = [r for r in records if not r['ok']]
versions = sorted({r['version'] for r in records if 'version' in r})
summary = dict(start=started, end=time.time(), requests=len(records), failures=len(failures),
               counts=dict(collections.Counter(r['kind'] for r in records)),
               initial_version=initial, expected_version=a.expected, observed_versions=versions,
               initial_backend=initial_backend, observed_backends=sorted({r['backend'] for r in records if r.get('backend')}),
               backend_changed=changed.is_set(),
               version_changed=initial != a.expected and a.expected in versions,
               in_flight=[r for r in records if r['kind']=='in_flight'],
               latency_ms_p95=round(latencies[int(len(latencies)*.95)],2) if latencies else None,
               latency_ms_max=round(max(latencies),2) if latencies else None,
               errors=failures[:10])
summary['passed'] = not failures and summary['backend_changed'] and a.expected in versions and any(r['ok'] for r in summary['in_flight'])
(out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['passed'] else 1)
