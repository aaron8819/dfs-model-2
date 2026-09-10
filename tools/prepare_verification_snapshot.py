"""Export reviewed Git blobs without transporting the private source repository's history."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT_FILES = {
    ".dockerignore",
    ".gitattributes",
    ".gitignore",
    ".nvmrc",
    "Dockerfile",
    "alembic.ini",
    "pyproject.toml",
    "requirements.lock",
    "requirements.txt",
    "AMD64_VERIFICATION_REPORT.md",
    "RELEASE_ACCEPTANCE.md",
    "INCREMENT_6_REPORT.md",
    "DEPLOYMENT_PLAN.md",
    "OPERATIONS_RUNBOOK.md",
    "docs/AMD64_VERIFICATION_PROCEDURE.md",
    "docs/AMD64_ACTIONS_HANDOFF.md",
    ".github/workflows/amd64-verification.yml",
}
TOOL_NAMES = {
    "completion_demo.py",
    "decision_demo.py",
    "synthetic_demo.py",
    "test_oidc.py",
    "image_acceptance.py",
    "image_polling.py",
    "late_swap_clock_test.py",
    "prepare_image.py",
    "amd64_verify.sh",
    "amd64_evidence.py",
    "amd64_evidence_test.py",
    "prepare_verification_snapshot.py",
}
SECRET = re.compile(
    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    rb"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:[^\s@]{12,}@)"
)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def selected(name: str, prior: bool = False) -> bool:
    if name.startswith("server/"):
        return name.endswith(".py") and name not in {
            "server/fixtures.py",
            "server/fixtures_test.py",
            "server/benchmark.py",
        }
    if name.startswith("tools/"):
        return name.removeprefix("tools/") in (
            {"completion_demo.py", "decision_demo.py", "synthetic_demo.py", "test_oidc.py"}
            if prior
            else TOOL_NAMES
        )
    if prior:
        return name == "pyproject.toml"
    if name.startswith("migrations/"):
        return name.endswith((".py", ".sql", ".mako"))
    if name.startswith("web/"):
        return name.endswith((".ts", ".tsx", ".css", ".html", ".json")) and (
            not name.startswith("web/e2e/")
            or name
            in {"web/e2e/decision.spec.ts", "web/e2e/late-swap.spec.ts", "web/e2e/mobile.spec.ts"}
        )
    return name in ROOT_FILES


def export(commit: str, destination: Path, prior: bool) -> dict:
    manifest = {}
    records = git("ls-tree", "-r", "-z", commit).split(b"\0")
    for record in filter(None, records):
        meta, raw_name = record.split(b"\t", 1)
        name = raw_name.decode()
        if not selected(name, prior):
            continue
        mode, kind, oid = meta.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Unexpected Git entry: {name}")
        data = git("cat-file", "blob", oid)
        if len(data) > 1_000_000 or SECRET.search(data) or b"\0" in data:
            raise ValueError(f"Manual review required (contents withheld): {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return {"source_commit": commit, "files": manifest}


def audit_history() -> dict:
    """Read every reachable blob; report metadata only, never matching contents."""
    objects = git("rev-list", "--objects", "--all").splitlines()
    paths = {}
    for line in objects:
        oid, _, name = line.partition(b" ")
        paths[oid] = name.decode(errors="replace")
    data = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=b"\n".join(paths) + b"\n",
        capture_output=True,
        check=True,
    ).stdout
    offset, blobs, total = 0, 0, 0
    findings = []
    while offset < len(data):
        end = data.index(b"\n", offset)
        oid, kind, size = data[offset:end].split()
        size = int(size)
        body = data[end + 1 : end + 1 + size]
        offset = end + size + 2
        if kind != b"blob":
            continue
        blobs += 1
        total += size
        path = paths[oid]
        reasons = []
        if path.startswith(("fixtures/", "artifacts/")):
            reasons.append("private fixture or historical artifact excluded")
        if SECRET.search(body):
            reasons.append("credential-pattern match; contents withheld")
        if size > 1_000_000:
            reasons.append("large blob")
        if reasons:
            findings.append({"blob": oid.decode(), "path": path, "bytes": size, "reasons": reasons})
    return {
        "reachable_blobs_read": blobs,
        "bytes_read": total,
        "findings": findings,
        "decision": "Never push original history; export reviewed allowlist to new root commit",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", default="HEAD")
    parser.add_argument("--prior", default="72f67ab")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise ValueError("Destination must not exist; no overwrite or deletion is performed")
    source = git("rev-parse", args.source + "^{commit}").decode().strip()
    prior = git("rev-parse", args.prior + "^{commit}").decode().strip()
    audit = audit_history()
    audit_path = Path("artifacts/local/amd64-history-audit.json")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    current = export(source, destination, False)
    previous = export(prior, destination / "verification/prior", True)
    manifest = {
        "format": 1,
        "current": current,
        "prior": previous,
        "excluded": "All original history, fixtures, historical artifacts, local env and databases",
    }
    (destination / "SOURCE_EQUIVALENCE.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "snapshot": str(destination),
                "source": source,
                "current_files": len(current["files"]),
                "prior_files": len(previous["files"]),
                "history_blobs_reviewed": audit["reachable_blobs_read"],
            }
        )
    )


if __name__ == "__main__":
    main()
