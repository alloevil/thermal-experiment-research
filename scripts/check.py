"""Check archive import and existing test suites without replacing study results."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def archive_path(relative):
    require(isinstance(relative, str) and relative and "\\" not in relative, "Invalid archive path")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == relative, "Unsafe archive path")
    current = ROOT
    for part in parsed.parts:
        current = current / part
        require(not current.is_symlink(), f"Imported archive cannot contain symlink: {relative}")
    require(current.is_file(), f"Missing imported file: {relative}")
    return current


def check_import():
    imported = json.loads((ROOT / "docs/archive-import.json").read_text())
    replacements = json.loads((ROOT / "docs/archive-replacements.json").read_text())
    exceptions = {item["path"]: item for item in replacements}
    require(len(exceptions) == len(replacements), "Duplicate archive replacement")
    seen = set()
    matched = 0
    for item in imported["files"]:
        relative = item["path"]
        require(relative not in seen, f"Duplicate import path: {relative}")
        seen.add(relative)
        expected = item["sha256"]
        if relative in exceptions:
            replacement = exceptions[relative]
            require(replacement["original_sha256"] == expected and replacement["reason"], "Unexplained replacement")
            if replacement.get("action") == "omitted":
                require(not (ROOT / relative).exists() and not (ROOT / relative).is_symlink(), f"Withheld reference restored: {relative}")
                notice = archive_path(replacement["notice_path"])
                require(hashlib.sha256(notice.read_bytes()).hexdigest() == replacement["notice_sha256"], f"Source notice changed: {relative}")
                matched += 1
                continue
            expected = replacement["replacement_sha256"]
        actual = hashlib.sha256(archive_path(relative).read_bytes()).hexdigest()
        require(actual == expected, f"Imported content changed: {relative}")
        matched += 1
    require(set(exceptions).issubset(seen), "Replacement is not in original archive")
    print(f"PASS archive import: {matched} files, {len(exceptions)} explicitly documented replacements", flush=True)


def run_suite(label, arguments):
    print(f"\n--- {label} ---", flush=True)
    environment = os.environ.copy()
    environment.update({"TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
                        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    environment.pop("PYTHONOPTIMIZE", None)
    command = [sys.executable, "-B", *arguments]
    completed = subprocess.run(command, cwd=ROOT, env=environment, timeout=300, check=False)
    require(completed.returncode == 0, f"{label} failed: exit {completed.returncode}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Archive and standard-library checks only")
    args = parser.parse_args(argv)
    try:
        check_import()
        run_suite("public reference boundaries", ["-S", "scripts/check_public_references.py"])
        run_suite("pinned stage snapshots", ["-S", "workbench.py", "check"])
        run_suite("standard-library entrypoints", ["-S", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
        if not args.quick:
            for label, directory in [("evidence report", "evidence_report"),
                                     ("next-experiment and review workflow", "next_experiment"),
                                     ("new thermal replay array checks", "tools/science_tests"),
                                     ("TCLab measured-data adapter and holdout evidence", "real_data/tclab")]:
                run_suite(label, ["-m", "unittest", "discover", "-s", directory, "-p", "test_*.py", "-v"])
        print("\nPASS selected repository checks; not a full scientific rerun or industrial validation", flush=True)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"Repository check failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
