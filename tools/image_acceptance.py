"""Synthetic whole-image resource and interruption drill on labeled local containers only."""

import csv
import io
import json
import subprocess
import time
from pathlib import Path

import httpx

from server import completion_test
from server.application_test import sign_in
from server.decision_test import apply, poll, post, read
from server.projections import HEADER
from tools.decision_demo import decision_demo


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def synthetic_pool() -> tuple:
    fixture = decision_demo()
    originals = list(csv.DictReader(io.StringIO(fixture["yahoo"])))
    rows = []
    for i in range(45):
        for original in originals:
            if original["Last Name"] == "Conflict" or original["Position"] == "DEF" and i:
                continue
            rows.append(
                {
                    **original,
                    "ID": f"nfl.{'t' if original['Position'] == 'DEF' else 'p'}.{700000+len(rows)}",
                    "Last Name": original["Last Name"]
                    + (f"Test{i}" if original["Position"] != "DEF" else ""),
                }
            )
    raw = io.StringIO()
    writer = csv.DictWriter(raw, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    files = {}
    for position in ("QB", "RB", "WR", "TE", "DST"):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        for i, row in enumerate(rows):
            if row["Position"] == ("DEF" if position == "DST" else position):
                writer.writerow(
                    [
                        1,
                        row["First Name"] + " " + row["Last Name"],
                        row["Team"],
                        "vs. " + row["Opponent"],
                        "3 stars",
                        "A",
                        str(10 + i % 17 / 100),
                    ]
                )
        files[position] = (position + ".csv", stream.getvalue().encode())
    fixture["setup"]["name"] = "Synthetic image resource acceptance"
    return fixture["setup"], raw.getvalue().encode(), files


def resources() -> dict:
    code = (
        "import json,pathlib; p=pathlib.Path('/sys/fs/cgroup'); "
        "print(json.dumps({k:(p/k).read_text() for k in "
        "['memory.current','memory.peak','memory.max','cpu.max','cpu.stat']}))"
    )
    return json.loads(docker("exec", "dfs-increment6-app", "python", "-c", code))


def main() -> None:
    for name in ("dfs-increment6-app", "dfs-increment6-postgres"):
        assert (
            json.loads(docker("inspect", name))[0]["Config"]["Labels"]["dfs.scope"] == "increment6"
        )
    measurements = {
        # These observations do not prove the physical host is native; retain host evidence too.
        "docker_architecture": docker("info", "--format", "{{.Architecture}}"),
        "container_machine": docker("exec", "dfs-increment6-app", "uname", "-m"),
        "before": resources(),
        "steps": {},
        "requests": [],
    }

    def started(request):
        request.extensions["started"] = time.perf_counter()

    def ended(response):
        measurements["requests"].append(
            {
                "method": response.request.method,
                "path": response.request.url.path,
                "status": response.status_code,
                "seconds": time.perf_counter() - response.request.extensions["started"],
            }
        )

    with httpx.Client(
        base_url="http://127.0.0.1:8765",
        timeout=45,
        event_hooks={"request": [started], "response": [ended]},
    ) as client:
        assert sign_in(client).status_code == 303
        client.headers.update(
            {
                "origin": "http://127.0.0.1:8765",
                "x-csrf-token": client.get("/api/session").json()["csrf"],
            },
        )
        completion_test.completion_demo = synthetic_pool
        start = time.perf_counter()
        w, files, context = completion_test.prepare(client)
        measurements["steps"]["yahoo_setup_import_seconds"] = time.perf_counter() - start
        start = time.perf_counter()
        w, review = completion_test.accept(
            client, w, completion_test.stage(client, w, files, context)
        )
        measurements["steps"]["five_projection_import_review_activate_seconds"] = (
            time.perf_counter() - start
        )
        measurements["coverage"] = review["coverage"]["summary"]
        for action in ("complete", "alternatives", "alternatives"):
            start = time.perf_counter()
            response = post(client, w, action)
            assert response.status_code == 202, response.text
            # A second tab can read while admission rejects a concurrent solve.
            assert client.get(f"/api/workspaces/{w['id']}").status_code == 200
            busy = post(client, w, "complete")
            assert busy.status_code == 409, busy.text
            result = poll(client, w, response)
            measurements["steps"].setdefault(action, []).append(
                {
                    "seconds": time.perf_counter() - start,
                    "status": result["status"],
                    "candidates": len(result["candidates"]),
                    "busy_status": busy.status_code,
                }
            )
            assert result["status"] == "ready", result
            if action == "complete":
                w = apply(client, w, result)
        measurements["before_shutdown"] = resources()
        # Ask for another real solve and wait until its native child exists before SIGTERM.
        response = post(client, w, "alternatives")
        assert response.status_code == 202
        rid = response.json()["request_id"]
        child_seen = False
        for _ in range(25):
            process_list = docker("top", "dfs-increment6-app", "-eo", "pid,args")
            if "worker.py" in process_list:
                child_seen = True
                break
            time.sleep(0.05)
        measurements["child_seen_before_shutdown"] = child_seen
        assert child_seen, "Must observe the real solver child before interruption"
        start = time.perf_counter()
        docker("stop", "-t", "40", "dfs-increment6-app")
        measurements["shutdown_seconds"] = time.perf_counter() - start
        measurements["exit"] = json.loads(docker("inspect", "dfs-increment6-app"))[0]["State"]
        docker("start", "dfs-increment6-app")
        ready = False
        for _ in range(100):
            try:
                if client.get("/ready").status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        assert ready, "Application did not regain readiness after restart"
        recovered = read(client, w)
        assert recovered["assignments"] == w["assignments"]
        result = client.get(f"/api/workspaces/{w['id']}/completions/{rid}").json()
        measurements["interrupted_status"] = result["status"]
        assert result["status"] == "interrupted", result
        assert post(client, w, f"completions/{rid}/apply").status_code == 409
        measurements["workspace"] = w["id"]
        measurements["after_restart"] = resources()
    Path("artifacts/increment6-image-resources.json").write_text(json.dumps(measurements, indent=2))
    print("Whole-image import/solve/busy/restart evidence recorded")


if __name__ == "__main__":
    main()
