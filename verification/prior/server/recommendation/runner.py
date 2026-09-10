"""One active child per checkout; bounded process isolation, NOT an OS security sandbox."""

import os
import subprocess
import sys
import sysconfig
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Lock
from time import perf_counter, sleep
from typing import Iterator

import psutil

from server.recommendation.contracts import SolveInput, SolveResult, input_hash, validate_input
from server.validator.lineup import validate_result

ROOT = Path(__file__).resolve().parents[2]
_ACTIVE = Lock()


class BusyError(RuntimeError):
    pass


def sanitized_environment(directory: Path) -> dict[str, str]:
    # An allowlist, not a credential-name denylist. Python uses an absolute executable.
    allowed = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    return {
        **allowed,
        "TEMP": str(directory),
        "TMP": str(directory),
        "TMPDIR": str(directory),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


@contextmanager
def active_solve() -> Iterator[None]:
    if not _ACTIVE.acquire(blocking=False):
        raise BusyError("one solve is already active")
    try:
        with (ROOT / ".runtime.lock").open("a+b") as handle:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise BusyError("another parent owns the runtime") from exc
            else:
                import fcntl

                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise BusyError("another parent owns the runtime") from exc
            # Closing the file releases the native lock, including exception/parent exit.
            yield
    finally:
        _ACTIVE.release()


def run_solve(
    data: SolveInput,
    budget_seconds: float = 30.0,
    hard_seconds: float = 35.0,
    cancel: Event | None = None,
) -> SolveResult:
    return _run_child(data, budget_seconds, hard_seconds, cancel)


def _run_child(
    data: SolveInput,
    budget_seconds: float,
    hard_seconds: float,
    cancel: Event | None = None,
    worker: Path | None = None,
) -> SolveResult:
    """Worker override is an internal deterministic fault-test seam, never serialized input."""
    if not 0 < budget_seconds <= hard_seconds <= 120:
        raise ValueError("expected 0 < budget <= hard deadline <= 120 seconds")
    validate_input(data)
    start = perf_counter()
    result = SolveResult(input_hash=input_hash(data), status="UNKNOWN", termination="budget")
    peak = 0
    with active_solve(), tempfile.TemporaryDirectory(prefix="dfs-solve-") as temp:
        directory = Path(temp)
        input_file = directory / "input.json"
        output_file = directory / "result.json"
        input_file.write_text(data.model_dump_json(), encoding="utf-8")
        child = subprocess.Popen(
            # Windows venv's redirector spawns a second process. Launch the base interpreter
            # directly so the tracked PID owns native work; pass the locked venv library path.
            [
                sys._base_executable if os.name == "nt" else sys.executable,
                "-I",
                str(worker or Path(__file__).with_name("worker.py")),
                str(input_file),
                str(output_file),
                str(start + budget_seconds),
                sysconfig.get_path("purelib"),
            ],
            env=sanitized_environment(directory),
            # Windows process exit can signal before its CWD handle is released.
            # Keep the CWD durable; all temporary I/O paths are explicit absolute paths.
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        process = psutil.Process(child.pid)
        stopped = None
        try:
            while child.poll() is None:
                if perf_counter() - start >= hard_seconds or (cancel and cancel.is_set()):
                    stopped = "interrupted" if cancel and cancel.is_set() else "budget"
                    child.kill()
                    break
                try:
                    memory = process.memory_info()
                    peak = max(peak, memory.rss, getattr(memory, "peak_wset", 0))
                except psutil.NoSuchProcess:
                    pass
                sleep(min(0.01, max(0.001, hard_seconds - (perf_counter() - start))))
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()  # Reap native work before releasing the admission lock or temp files.
            if os.name == "nt":
                # Popen has no public handle-close method. Release the signaled Windows
                # process handle now instead of waiting for garbage collection.
                child._handle.Close()
        if output_file.exists():
            try:
                if output_file.stat().st_size > 1_000_000:
                    raise ValueError("oversized output")
                candidate = SolveResult.model_validate_json(output_file.read_bytes())
                validation_seconds = validate_result(data, candidate)
                result = candidate.model_copy(update={"validator_seconds": validation_seconds})
            except (ValueError, OSError) as exc:
                result = result.model_copy(
                    update={
                        "status": "INVALID",
                        "termination": "invalid",
                        "detail": "rejected child output: " + str(exc)[:300],
                    }
                )
        if stopped:
            # A checkpoint only carries proofs completed before termination.
            result = result.model_copy(update={"termination": stopped})
        elif child.returncode != 0:
            result = result.model_copy(
                update={
                    "termination": "unexpected_exit",
                    "detail": f"child exited {child.returncode}",
                }
            )
        elif not output_file.exists():
            result = result.model_copy(
                update={
                    "status": "INVALID",
                    "termination": "invalid",
                    "detail": "missing child output",
                }
            )
    result = result.model_copy(
        update={
            "elapsed_seconds": perf_counter() - start,
            "peak_rss_bytes": peak,
        }
    )
    validate_result(data, result)
    return result
