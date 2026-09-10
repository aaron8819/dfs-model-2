"""Private child entrypoint; explicit files only, isolated Python import configuration."""

import os
import sys
from pathlib import Path
from time import perf_counter

# -I discards PYTHONPATH and user site packages. Load only this checkout explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, sys.argv[4])


def main() -> None:
    from server.recommendation.contracts import SolveInput, SolveResult
    from server.recommendation.solver import solve

    input_path, output_path = map(Path, sys.argv[1:3])
    data = SolveInput.model_validate_json(input_path.read_bytes())

    def publish(result: SolveResult) -> None:
        temporary = output_path.with_suffix(".tmp")
        temporary.write_text(result.model_dump_json(), encoding="utf-8")
        os.replace(temporary, output_path)

    solve(data, max(0.0, float(sys.argv[3]) - perf_counter()), publish)


if __name__ == "__main__":
    main()
