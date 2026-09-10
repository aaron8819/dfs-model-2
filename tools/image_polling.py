"""Measure two authenticated tabs during a real solve; local image and isolated DB only."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import psycopg

from server.application_test import sign_in
from server.decision_test import poll, post


def main() -> None:
    wid = json.loads(Path("artifacts/increment6-image-resources.json").read_text())["workspace"]
    stop = threading.Event()
    connections = []

    def monitor() -> None:
        with psycopg.connect(
            host="127.0.0.1", port=55436, dbname="dfs_release", user="postgres", autocommit=True
        ) as db:
            while not stop.wait(0.05):
                connections.append(
                    db.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname='dfs_release' "
                        "AND usename='dfs_runtime'"
                    ).fetchone()[0]
                )

    def size() -> dict:
        with psycopg.connect(
            host="127.0.0.1", port=55436, dbname="dfs_release", user="dfs_runtime"
        ) as db:
            row = db.execute(
                "SELECT pg_database_size(current_database()), "
                "(SELECT coalesce(sum(octet_length(bytes)),0) FROM raw_blob), "
                "(SELECT count(*) FROM draft_revision), "
                "(SELECT count(*) FROM recommendation_request)"
            ).fetchone()
            return dict(zip(("database_bytes", "source_bytes", "draft_revisions", "requests"), row))

    result = {"before": size()}
    with httpx.Client(base_url="http://127.0.0.1:8765", timeout=40) as client:
        assert sign_in(client).status_code == 303
        client.headers.update(
            {
                "origin": "http://127.0.0.1:8765",
                "x-csrf-token": client.get("/api/session").json()["csrf"],
            }
        )
        w = client.get(f"/api/workspaces/{wid}").json()
        thread = threading.Thread(target=monitor)
        thread.start()
        response = post(client, w, "alternatives")
        assert response.status_code == 202

        def tab(_: int) -> list[float]:
            values = []
            with httpx.Client(
                base_url="http://127.0.0.1:8765", cookies=client.cookies, timeout=20
            ) as reader:
                for _ in range(12):
                    start = time.perf_counter()
                    assert reader.get(f"/api/workspaces/{wid}").status_code == 200
                    assert reader.get(f"/api/workspaces/{wid}/analysis").status_code == 200
                    values.append(time.perf_counter() - start)
                    time.sleep(0.2)
            return values

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                result["two_tab_workspace_plus_research_seconds"] = list(pool.map(tab, range(2)))
            solved = poll(client, w, response)
            assert solved["status"] == "ready"
            result["solver_status"] = solved["status"]
        finally:
            stop.set()
            thread.join(5)
    result["runtime_connections_peak"] = max(connections)
    result["connection_samples"] = len(connections)
    result["after"] = size()
    Path("artifacts/increment6-image-polling.json").write_text(
        json.dumps(result, indent=2, default=int)
    )


if __name__ == "__main__":
    main()
