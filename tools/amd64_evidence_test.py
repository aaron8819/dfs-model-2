"""Safety boundaries for the snapshot and artifact handoff, without Docker or GitHub."""

import hashlib
import json
from pathlib import Path

import pytest

from tools import amd64_evidence as evidence
from tools.prepare_verification_snapshot import SECRET, selected


def test_snapshot_allowlist_excludes_private_material() -> None:
    for name in (
        "fixtures/private/historical/raw/yahoo.csv",
        "artifacts/increment6-mobile.json",
        ".env.local.json",
        "database.dump",
        "server/fixtures.py",
        "tools/preserve_fixtures.py",
    ):
        assert not selected(name)
        assert not selected(name, prior=True)
    assert selected("server/app.py") and selected("server/app.py", prior=True)
    assert selected("migrations/versions/0005_increment6.sql")
    assert SECRET.search(b"ghp_" + b"a" * 36)


def test_manifest_rejects_changed_and_extra_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("app.py").write_bytes(b"reviewed")
    manifest = {
        "current": {
            "files": {
                "app.py": {
                    "bytes": 8,
                    "sha256": hashlib.sha256(b"reviewed").hexdigest(),
                }
            }
        },
        "prior": {"files": {}},
    }
    Path("SOURCE_EQUIVALENCE.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(
        evidence.subprocess, "check_output", lambda *a, **k: "app.py\nSOURCE_EQUIVALENCE.json\n"
    )
    evidence.verify_source()
    Path("app.py").write_bytes(b"modified")
    with pytest.raises(AssertionError):
        evidence.verify_source()
    Path("app.py").write_bytes(b"reviewed")
    monkeypatch.setattr(
        evidence.subprocess,
        "check_output",
        lambda *a, **k: "app.py\nSOURCE_EQUIVALENCE.json\nprivate.dump\n",
    )
    with pytest.raises(AssertionError):
        evidence.verify_source()


def test_artifact_collection_excludes_failure_payloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    evidence.RUN.mkdir(parents=True)
    (evidence.RUN / "regressions.xml").write_text(
        '<testsuite><testcase name="boundary" classname="test" time="1">'
        "<failure>session-cookie-private</failure></testcase></testsuite>"
    )
    (evidence.RUN / "private.dump").write_bytes(b"private-database")
    (evidence.RUN / "browser.json").write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "specs": [
                            {
                                "title": "browser",
                                "tests": [
                                    {
                                        "status": "unexpected",
                                        "results": [
                                            {
                                                "status": "failed",
                                                "duration": 12,
                                                "retry": 0,
                                                "error": "session-cookie-private",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ],
                "stats": {},
            }
        )
    )
    monkeypatch.setattr(evidence, "docker", lambda *a: '{"Running": false}')
    evidence.collect()
    folder = Path("artifacts/local/amd64-upload")
    data = b"".join(p.read_bytes() for p in folder.iterdir())
    assert b"session-cookie-private" not in data and b"private-database" not in data
    assert b'"failure"' in data and b'"failed"' in data
