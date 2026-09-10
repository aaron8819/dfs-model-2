import json
from pathlib import Path
from threading import Event
from time import perf_counter, sleep

import psutil
import pytest

from server.recommendation.runner import (
    BusyError,
    _run_child,
    active_solve,
    run_solve,
    sanitized_environment,
)
from server.recommendation.solver import solve
from server.recommendation.solver_test import tiny


def worker_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fault_worker.py"
    path.write_text(body, encoding="utf-8")
    return path


def assert_reaped(pid: int) -> None:
    # Windows can expose a signaled, exited process in its PID table briefly after wait().
    # Native work has stopped; bound the OS teardown observation separately from solving.
    until = perf_counter() + 1.0
    while psutil.pid_exists(pid) and perf_counter() < until:
        sleep(0.01)
    assert not psutil.pid_exists(pid)


def test_real_child_roundtrip() -> None:
    result = run_solve(tiny())
    assert result.primary_proven and result.tie_complete
    assert result.peak_rss_bytes > 0


def test_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sentinel-no-real-secret")
    monkeypatch.setenv("AUTH_SECRET", "sentinel-no-real-secret")
    monkeypatch.setenv("UNRELATED_APP_CREDENTIAL", "sentinel-no-real-secret")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    allowed = sanitized_environment(tmp_path)
    assert set(k.upper() for k in allowed) <= {
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    }
    evidence = tmp_path / "child_env.json"
    script = worker_file(
        tmp_path,
        "import os,json,pathlib,sys\n"
        f"pathlib.Path({str(evidence)!r}).write_text(json.dumps(dict(os.environ)))\n",
    )
    _run_child(tiny(), 5.0, 6.0, worker=script)
    environment = json.loads(evidence.read_text())
    assert not {"DATABASE_URL", "AUTH_SECRET", "UNRELATED_APP_CREDENTIAL", "PYTHONPATH"} & (
        environment.keys()
    )


@pytest.mark.parametrize("mode", ["deadline", "cancel", "checkpoint"])
def test_termination_reaps_and_cleans(tmp_path: Path, mode: str) -> None:
    evidence = tmp_path / "pid.json"
    checkpoint = solve(tiny()).model_copy(
        update={"tie_complete": False, "stages": solve(tiny()).stages[:1], "termination": "budget"}
    )
    script = worker_file(
        tmp_path,
        "import os,json,pathlib,sys,time\n"
        f"pathlib.Path({str(evidence)!r}).write_text(json.dumps([os.getpid(),sys.argv[1]]))\n"
        + (
            f"pathlib.Path(sys.argv[2]).write_text({checkpoint.model_dump_json()!r})\n"
            if mode == "checkpoint"
            else ""
        )
        + "while True:\n    time.sleep(0.01)\n",
    )
    cancel = Event()
    # Timer produces a deterministic external interruption, not a rare CP-SAT status.
    if mode == "cancel":
        from threading import Timer

        timer = Timer(0.8, cancel.set)
        timer.start()
    start = perf_counter()
    result = _run_child(tiny(), 1.0, 1.2, cancel=cancel, worker=script)
    assert perf_counter() - start < 4
    pid, input_path = json.loads(evidence.read_text())
    assert_reaped(pid)
    assert not Path(input_path).parent.exists()
    assert result.termination == ("interrupted" if mode == "cancel" else "budget")
    if mode == "checkpoint":
        assert result.primary_proven and result.assignments and not result.tie_complete
    else:
        assert result.status == "UNKNOWN" and not result.assignments
    with active_solve():
        pass  # Admission lock was released after reaping.


@pytest.mark.parametrize(
    ("body", "status", "termination"),
    [
        ("import sys; sys.exit(7)", "UNKNOWN", "unexpected_exit"),
        ("pass", "INVALID", "invalid"),
        (
            "import sys,pathlib; pathlib.Path(sys.argv[2]).write_text('{broken')",
            "INVALID",
            "invalid",
        ),
        (
            "import sys,pathlib; pathlib.Path(sys.argv[2]).write_text('x'*1000001)",
            "INVALID",
            "invalid",
        ),
    ],
)
def test_fault_outputs(tmp_path: Path, body: str, status: str, termination: str) -> None:
    result = _run_child(tiny(), 5.0, 6.0, worker=worker_file(tmp_path, body))
    assert result.status == status and result.termination == termination
    assert not result.assignments


def test_busy_and_invalid_budget() -> None:
    with active_solve(), pytest.raises(BusyError):
        run_solve(tiny())
    for soft, hard in [(0.0, 1.0), (2.0, 1.0), (1.0, 121.0), (float("nan"), 2.0)]:
        with pytest.raises(ValueError):
            run_solve(tiny(), soft, hard)


def test_native_work_is_killed(tmp_path: Path) -> None:
    evidence = tmp_path / "native.json"
    script = worker_file(
        tmp_path,
        "import sys,pathlib,json,os\n"
        "sys.path.insert(0,sys.argv[4])\n"
        "from ortools.sat.python import cp_model\n"
        "m=cp_model.CpModel()\n"
        "xs=[m.new_bool_var(str(i)) for i in range(40)]\n"
        "m.add(sum(xs)==20)\n"
        "class Probe(cp_model.CpSolverSolutionCallback):\n"
        "    def on_solution_callback(self):\n"
        f"        p=pathlib.Path({str(evidence)!r})\n"
        "        if not p.exists(): p.write_text(json.dumps([os.getpid(),sys.argv[1]]))\n"
        "s=cp_model.CpSolver()\n"
        "s.parameters.enumerate_all_solutions=True\n"
        "s.parameters.num_search_workers=1\n"
        "s.solve(m,Probe())\n",
    )
    # WSL loading native wheels from a Windows-mounted venv can take several seconds.
    result = _run_child(tiny(), 25.0, 30.0, worker=script)
    pid, input_path = json.loads(evidence.read_text())
    assert result.termination == "budget" and result.status == "UNKNOWN"
    assert_reaped(pid)
    assert not Path(input_path).parent.exists()
    assert result.elapsed_seconds < 32


def test_cross_parent_admission(tmp_path: Path) -> None:
    import subprocess
    import sys

    from server.recommendation.runner import ROOT

    script = worker_file(
        tmp_path,
        "from server.recommendation.runner import active_solve,BusyError\n"
        "try:\n"
        "    with active_solve(): raise RuntimeError('admitted twice')\n"
        "except BusyError: pass\n",
    )
    with active_solve():
        process = subprocess.run(
            [sys.executable, "-c", script.read_text()], cwd=ROOT, timeout=10, check=False
        )
    assert process.returncode == 0


def test_parent_rejects_false_totals_and_retains_checkpoint_on_exit(tmp_path: Path) -> None:
    valid = solve(tiny()).model_copy(update={"tie_complete": False})
    bad = valid.model_copy(update={"salary_cents": 1})
    for candidate, expected in ((bad, "INVALID"), (valid, "OPTIMAL")):
        script = worker_file(
            tmp_path,
            "import pathlib,sys\n"
            f"pathlib.Path(sys.argv[2]).write_text({candidate.model_dump_json()!r})\n"
            "sys.exit(7)\n",
        )
        result = _run_child(tiny(), 5.0, 6.0, worker=script)
        assert result.status == expected and result.termination == "unexpected_exit"
        assert bool(result.assignments) == (expected == "OPTIMAL")
