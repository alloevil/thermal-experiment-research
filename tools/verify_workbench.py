"""Exercise the real read-only entry points without changing study artifacts."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import workbench


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def snapshot():
    records = {}
    for name, _, _, _ in workbench.STAGES:
        for directory, subdirectories, filenames in os.walk(ROOT / name):
            subdirectories[:] = [entry for entry in subdirectories if entry != ".venv"]
            for filename in filenames:
                path = Path(directory) / filename
                stat = path.stat()
                records[str(path.relative_to(ROOT))] = (stat.st_size, stat.st_mtime_ns, workbench.sha256(path))
    return records


def main():
    before = snapshot()
    interpreter = ROOT / "feasibility/.venv/bin/python"
    require(interpreter.is_file(), "Integration report check requires the documented local environment")
    command = str(ROOT / "workbench.py")
    with tempfile.TemporaryDirectory(prefix="thermal-entrypoint-") as temporary:
        def launch(arguments, executable=sys.executable, flags=("-I", "-B", "-S")):
            return subprocess.run([str(executable), *flags, command, *arguments],
                                  cwd=temporary, text=True, capture_output=True, check=False)
        listing = launch(["list", "--json"])
        require(listing.returncode == 0, listing.stderr)
        require(json.loads(listing.stdout)["status"] == "not_checked", "Listing must not claim validation")
        checked = launch(["check", "--json"])
        require(checked.returncode == 0, checked.stderr)
        data = json.loads(checked.stdout)
        require(data["verified_artifacts"] == 1186 and len(data["stages"]) == 8, "Incomplete snapshot check")
        optimized = launch(["check", "--json"], flags=("-I", "-B", "-S", "-O"))
        require(optimized.returncode == 0 and optimized.stdout == checked.stdout, "Checks differ under -O")
        invalid = launch(["check", "../outside"])
        require(invalid.returncode == 2 and not invalid.stdout, "Unknown stage did not fail closed")
        print("PASS standard-library list/check from unrelated cwd; all 1186 pinned entries matched")
        print("PASS python -O retains checks; invalid stage exits 2 with no report")
        for output_format, extension in [("json", "json"), ("markdown", "md")]:
            report = launch(["report", "--format", output_format], executable=interpreter, flags=("-I", "-B"))
            require(report.returncode == 0, report.stderr)
            expected = (ROOT / f"evidence_report/results/reference-evidence.{extension}").read_text()
            require(report.stdout == expected, f"{output_format} differs from prior evidence report")
            if output_format == "json":
                require(json.loads(report.stdout)["engineering_release"] == "not_supported", "Unexpected engineering release")
        print("PASS real JSON/Markdown report forwarding matches prior outputs; no release assertion")
    after = snapshot()
    require(before == after, "Study file set, content or modification times changed during entrypoint operations")
    print(f"PASS {len(before)} prior-stage files unchanged in content, size and mtime; no added/removed files")
    print("SCOPE virtual environment excluded from write audit; no numerical experiment or physical validation performed")


if __name__ == "__main__":
    main()
