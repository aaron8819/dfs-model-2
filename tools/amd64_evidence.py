"""Verify snapshot equivalence and collect an explicit, credential-free evidence allowlist."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

RUN = Path("artifacts/local/amd64-run")
SAFE_JSON = (
    "increment6-image-resources.json",
    "increment6-image-polling.json",
    "increment6-image-browser-evidence.json",
    "increment6-decisions-browser-evidence.json",
    "increment6-wheels-amd64.json",
)
SAFE_RUN = (
    "runtime-checks.txt",
    "build-inputs.txt",
    "unavailable-handler.json",
    "production-rejection.txt",
    "source.txt",
    "source-equivalence.json",
    "host.txt",
    "daemon.txt",
    "runner.txt",
    "native-attestation.txt",
    "images.json",
    "postgres-image.json",
    "runtime-packages.json",
    "before.json",
    "after.json",
    "start-time.txt",
    "ready-time.txt",
    "app-limits.json",
    "startup-controls.txt",
    "grant-denials.txt",
    "final.json",
)


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, timeout=15).strip()


def verify_source() -> None:
    manifest = json.loads(Path("SOURCE_EQUIVALENCE.json").read_text())
    expected = {"SOURCE_EQUIVALENCE.json"}
    for group, root in (("current", Path(".")), ("prior", Path("verification/prior"))):
        for name, metadata in manifest[group]["files"].items():
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(Path.cwd().resolve()):
                raise ValueError("Unsafe manifest path")
            data = path.read_bytes()
            assert (
                len(data) == metadata["bytes"]
                and hashlib.sha256(data).hexdigest() == metadata["sha256"]
            ), name
            expected.add(path.as_posix())
    tracked = set(subprocess.check_output(["git", "ls-files"], text=True).splitlines())
    assert tracked == expected, "Snapshot contains missing or unmanifested files"
    print("Every snapshot file matches its recorded source blob SHA-256")


def final() -> None:
    from tools.image_acceptance import resources

    state = json.loads(docker("inspect", "--format", "{{json .State}}", "dfs-increment6-app"))
    assert state["Running"] and not state["OOMKilled"]
    processes = docker("top", "dfs-increment6-app", "-eo", "pid,args")
    assert "worker.py" not in processes, "Surviving solver child"
    result = {
        "status": "completed",
        "source": os.environ["GITHUB_SHA"],
        "startup_seconds": float((RUN / "ready-time.txt").read_text())
        - float((RUN / "start-time.txt").read_text()),
        "post_browser_resources": resources(),
        "post_browser_memory_events": docker(
            "exec", "dfs-increment6-app", "cat", "/sys/fs/cgroup/memory.events"
        ),
        "no_surviving_child": True,
        "outage_reconnection": "pending; no fault injection performed",
        "identity": "development synthetic OIDC; separate production rejection control",
    }
    (RUN / "final.json").write_text(json.dumps(result, indent=2) + "\n")


def collect() -> None:
    destination = Path("artifacts/local/amd64-upload")
    destination.mkdir(parents=True, exist_ok=True)
    for root, names in ((RUN, SAFE_RUN), (Path("artifacts"), SAFE_JSON)):
        for name in names:
            path = root / name
            if path.is_file():
                shutil.copyfile(path, destination / name)
    screenshots = [
        f"increment6-mobile-{width}-{section}.png"
        for width in (320, 390, 430)
        for section in ("briefing", "players", "lineup", "previews")
    ] + [
        f"increment6-image-{state}.png" for state in ("fixed", "remainder", "conflict", "reconcile")
    ]
    for name in screenshots:
        path = Path("artifacts") / name
        if path.is_file():
            shutil.copyfile(path, destination / name)
    # JUnit failures can echo locals or response bodies: retain only test identities/status/timing.
    for name in ("prior-synthetic.xml", "regressions.xml"):
        path = RUN / name
        if not path.exists():
            continue
        tests = []
        for case in ET.parse(path).iter("testcase"):
            status = next(
                (s for s in ("failure", "error", "skipped") if case.find(s) is not None), "passed"
            )
            tests.append(
                {k: case.get(k) for k in ("classname", "name", "time")} | {"status": status}
            )
        (destination / (name + ".json")).write_text(json.dumps(tests, indent=2) + "\n")
    for name in ("browser.json", "mobile.json"):
        path = RUN / name
        if path.exists():
            report = json.loads(path.read_text())
            # Browser error payloads/attachments may contain session material; omit them.
            tests = []

            def walk(suite: dict) -> None:
                for spec in suite.get("specs", []):
                    for test in spec["tests"]:
                        tests.append(
                            {
                                "title": spec["title"],
                                "status": test["status"],
                                "results": [
                                    {k: r.get(k) for k in ("status", "duration", "retry")}
                                    for r in test["results"]
                                ],
                            }
                        )
                for child in suite.get("suites", []):
                    walk(child)

            walk(report)
            (destination / name).write_text(
                json.dumps({"tests": tests, "stats": report.get("stats")}, indent=2) + "\n"
            )
    diagnostics = {}
    for name in (
        "dfs-increment6-app",
        "dfs-increment6-postgres",
        "dfs-amd64-tests",
        "dfs-amd64-oidc",
    ):
        try:
            diagnostics[name] = json.loads(docker("inspect", "--format", "{{json .State}}", name))
        except subprocess.SubprocessError:
            diagnostics[name] = {"state": "not available"}
    (destination / "container-states.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
    assert (
        sum(p.stat().st_size for p in destination.iterdir()) <= 20 * 1024 * 1024
    ), "Artifact exceeds 20 MiB budget"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("verify-source", "final", "collect"))
    args = parser.parse_args()
    {"verify-source": verify_source, "final": final, "collect": collect}[args.operation]()


if __name__ == "__main__":
    main()
