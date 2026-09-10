"""Prepare locked Linux wheels and record hashes before an offline Docker build."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("architecture", choices=["arm64", "amd64"])
    args = parser.parse_args()
    machine = "aarch64" if args.architecture == "arm64" else "x86_64"
    folder = Path(f"artifacts/local/wheels-{args.architecture}")
    platforms = ["manylinux2014", "manylinux_2_24", "manylinux_2_27", "manylinux_2_28"]
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--python-version",
        "313",
        "--implementation",
        "cp",
        "--abi",
        "cp313",
        "--dest",
        str(folder),
        "-r",
        "requirements.lock",
    ]
    for platform in platforms:
        command.extend(["--platform", f"{platform}_{machine}"])
    subprocess.run(command, check=True)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.whl"))
    }
    Path(f"artifacts/increment6-wheels-{args.architecture}.json").write_text(
        json.dumps(hashes, indent=2)
    )


if __name__ == "__main__":
    main()
