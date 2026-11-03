"""Lance une série de générations via l'API d'AI STUDIO et journalise le résultat de chacune.

    ~/ComfyUI/.venv/bin/python tools/test_suite.py tools/cases_v5.json > data/test_suite.log
"""
import json
import sys
import time
import urllib.error
import urllib.request

B = "http://127.0.0.1:8190"


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}


def wait(ids, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            jobs = {j["id"]: j for j in call("/api/jobs")["jobs"]}
        except Exception:
            time.sleep(5)
            continue
        cur = [jobs[i] for i in ids if i in jobs]
        if cur and all(j["status"] in ("done", "error", "cancelled") for j in cur):
            return cur
        time.sleep(5)
    return [jobs.get(i, {"status": "timeout"}) for i in ids]


for case in json.load(open(sys.argv[1])):
    name = case.pop("_name")
    t = time.time()
    r = call("/api/generate", case)
    if "jobs" not in r:
        print(f"REFUS  {name}: {r}", flush=True)
        continue
    done = wait([j["id"] for j in r["jobs"]])
    for j in done:
        outs = ", ".join(o["filename"] for o in j.get("outputs", []))
        status = j.get("status")
        print(f"{'OK   ' if status == 'done' and outs else 'ÉCHEC'}  {name:28} {time.time() - t:6.0f}s  {outs or j.get('error', '')[:200]}", flush=True)
print("FIN", flush=True)
