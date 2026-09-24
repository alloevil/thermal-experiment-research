"""Explicitly install a minimal environment and test a relocated evidence snapshot."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from workbench import STAGES, check_snapshots, file_path, parse_manifest, sha256


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def inventory(root):
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns, sha256(path))
            for path in root.rglob("*") if path.is_file()}


def copy_snapshot(source, destination):
    require(not destination.exists(), "Destination must not already exist")
    checked = check_snapshots(source, STAGES)
    require(checked["status"] == "matched_snapshot", "Source snapshot is invalid")
    paths = ["workbench.py", "tests/test_workbench.py"]
    for name, _, _, _ in STAGES:
        manifest_name = f"{name}/results/artifact-manifest.json"
        manifest = file_path(source, manifest_name)
        paths.append(manifest_name)
        paths.extend(f"{name}/{entry['file']}" for entry in parse_manifest(manifest.read_bytes()))
    require(len(paths) == len(set(paths)), "Duplicate copy entries")
    for relative in paths:
        origin = file_path(source, relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        require(sha256(origin) == sha256(target), f"Copy changed: {relative}")
    require(check_snapshots(destination, STAGES)["status"] == "matched_snapshot", "Copied snapshot is invalid")
    return len(paths)


def clean_environment():
    environment = dict(os.environ)
    for name in list(environment):
        if name.startswith("PYTHON") or name in {"VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"}:
            environment.pop(name)
    environment.update({"TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
                        "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    return environment


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-install", action="store_true", help="Explicit permission to fetch the locked NumPy wheel into a temporary venv")
    args = parser.parse_args(argv)
    require(args.allow_install, "Pass --allow-install: this audit installs NumPy from PyPI into a temporary environment")
    installer = shutil.which("uv")
    require(installer is not None, "uv must be installed explicitly before this audit")
    evidence = ROOT / "tools/results/isolated-report"
    require(not evidence.exists(), "Archive the previous isolated-report directory before rerunning")
    evidence.mkdir()
    started = time.perf_counter()
    events = []
    environment = clean_environment()

    def execute(label, command, cwd, expected=0):
        result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True,
                                timeout=240, check=False)
        (evidence / f"{label}.stdout.txt").write_text(result.stdout)
        (evidence / f"{label}.stderr.txt").write_text(result.stderr)
        events.append({"label": label, "command": [str(part) for part in command], "exit_code": result.returncode})
        (evidence / "commands.json").write_text(json.dumps(events, indent=2) + "\n")
        require(result.returncode == expected, f"{label}: expected exit {expected}, got {result.returncode}; see logs")
        return result

    before = check_snapshots(ROOT, STAGES)
    require(before["status"] == "matched_snapshot", "Source is not at pinned state")
    with tempfile.TemporaryDirectory(prefix="thermal-isolated-") as temporary:
        temporary = Path(temporary)
        project = temporary / "relocated snapshot 中文"
        copied_count = copy_snapshot(ROOT, project)
        before_copy = inventory(project)
        working_directory = temporary / "unrelated cwd"
        working_directory.mkdir()
        environment_path = temporary / "minimal python"
        venv.EnvBuilder(with_pip=False, system_site_packages=False).create(environment_path)
        interpreter = environment_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        command = [str(interpreter), "-I", "-B", str(project / "workbench.py")]
        probe_source = (
            "import importlib.util,importlib.metadata,json,sys; "
            "print(json.dumps({'python':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
            "'numpy_available':importlib.util.find_spec('numpy') is not None,"
            "'packages':{d.metadata['Name'].lower():d.version for d in importlib.metadata.distributions()}}))"
        )
        empty = execute("empty-environment", [str(interpreter), "-I", "-B", "-c", probe_source], working_directory)
        empty_data = json.loads(empty.stdout)
        require(not empty_data["numpy_available"] and empty_data["packages"] == {}, "New venv unexpectedly inherits packages")
        require(empty_data["prefix"] != empty_data["base_prefix"], "Not a virtual environment")
        require(not (project / "feasibility/.venv").exists(), "Original virtual environment was copied")
        execute("list-empty", [*command, "list", "--json"], working_directory)
        check = execute("check-empty", [*command, "check", "--json"], working_directory)
        require(json.loads(check.stdout)["verified_artifacts"] == 1186, "Incomplete check")
        missing = execute("report-missing-numpy", [*command, "report", "--format", "json"], working_directory, expected=2)
        require(missing.stdout == "" and "NumPy" in missing.stderr, "Missing dependency path did not fail as documented")
        print("PASS fresh venv has zero packages; copied list/check work; report rejects missing NumPy", flush=True)
        execute("install", [installer, "--no-config", "--no-cache", "pip", "install", "--python", str(interpreter),
                            "--require-hashes", "--only-binary", ":all:", "--index-url", "https://pypi.org/simple",
                            "-r", str(ROOT / "requirements-report.lock")], working_directory)
        installed = execute("installed-environment", [str(interpreter), "-I", "-B", "-c", probe_source], working_directory)
        metadata = json.loads(installed.stdout)
        require(metadata["packages"] == {"numpy": "2.5.3"}, "Unexpected installed packages")
        module = execute("numpy-origin", [str(interpreter), "-I", "-B", "-c",
                         "import numpy,json; print(json.dumps({'file':numpy.__file__,'version':numpy.__version__}))"], working_directory)
        module_path = Path(json.loads(module.stdout)["file"]).resolve()
        require(module_path.is_relative_to(environment_path.resolve()), "NumPy was loaded outside the isolated venv")
        execute("dependencies", [installer, "--no-config", "pip", "check", "--python", str(interpreter)], working_directory)
        print("PASS isolated install contains only hash-locked NumPy 2.5.3; import originates inside the venv", flush=True)
        for format_name, suffix in [("json", "json"), ("markdown", "md")]:
            result = execute(f"report-{format_name}", [*command, "report", "--format", format_name], working_directory)
            expected = (project / f"evidence_report/results/reference-evidence.{suffix}").read_text()
            require(result.stdout == expected, f"Relocated {format_name} report differs")
        optimized = execute("report-optimized", [str(interpreter), "-I", "-B", "-O", str(project / "workbench.py"),
                                                  "report", "--format", "json"], working_directory)
        require(optimized.stdout == (project / "evidence_report/results/reference-evidence.json").read_text(), "-O output differs")
        execute("workbench-tests", [str(interpreter), "-I", "-B", "-S", "-m", "unittest", "discover", "-s", str(project / "tests"), "-v"], working_directory)
        execute("evidence-tests", [str(interpreter), "-I", "-B", "-m", "unittest", "discover", "-s", str(project / "evidence_report"), "-p", "test_*.py", "-v"], working_directory)
        require(before_copy == inventory(project), "Relocated file set, content or mtime changed")
        print("PASS relocated JSON/Markdown/-O reports are byte-identical; 17 entrypoint and 14 report tests pass", flush=True)
        byte_count = sum(size for size, _, _ in before_copy.values())
        venv_bytes = sum(path.stat().st_size for path in environment_path.rglob("*") if path.is_file() and not path.is_symlink())
        receipt = {"status": "PASS", "copied_files": copied_count, "copied_bytes": byte_count,
                   "venv_regular_file_bytes": venv_bytes, "environment": metadata,
                   "lock_sha256": sha256(ROOT / "requirements-report.lock"),
                   "read_only_copy_verified": True, "elapsed_seconds": time.perf_counter() - started,
                   "scope": "Fresh venv and relocated files on the same OS/CPU/base Python; not another machine, full science rerun, or distribution license review."}
    require(check_snapshots(ROOT, STAGES) == before, "Original snapshot changed")
    (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PASS {copied_count} relocated files unchanged; original pinned stages unchanged; temporary venv/copy removed", flush=True)
    print("LIMIT: same-host isolation only, no cross-platform or full scientific reproduction claim", flush=True)


if __name__ == "__main__":
    main()
