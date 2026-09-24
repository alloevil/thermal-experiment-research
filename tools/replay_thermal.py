"""Run the frozen thermal example in a new directory using an explicit Python."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from workbench import STAGES, check_stage, file_path, parse_manifest, sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(output):
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), "Output directory already exists; archive it or choose a new path")
    for name, _, _, _ in STAGES:
        require(not output.resolve().is_relative_to((ROOT / name).resolve()), "Output cannot be inside an archived study")
    stage = next(stage for stage in STAGES if stage[0] == "radiation")
    require(check_stage(ROOT, stage)["status"] == "matched_snapshot", "Frozen radiation snapshot is invalid")
    manifest = parse_manifest((ROOT / "radiation/results/artifact-manifest.json").read_bytes())
    expected = {item["file"]: item["sha256"] for item in manifest}
    filenames = ["model.py", "check_model.py", "experiment.py", "protocol.md", "results/protocol-sha256.txt"]
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    (output / "logs").mkdir()
    copied = []
    for name in filenames + ["results/experiment.json"]:
        source = file_path(ROOT / "radiation", name)
        require(sha256(source) == expected[name], f"Source changed: {name}")
        target = output / ("reference-experiment.json" if name == "results/experiment.json" else name)
        shutil.copyfile(source, target)
        require(sha256(target) == expected[name], "Copy hash mismatch")
        copied.append({"file": str(target.relative_to(output)), "source": f"radiation/{name}", "sha256": expected[name]})
    checker = ROOT / "tools/check_thermal_replay.py"
    shutil.copyfile(checker, output / "check_replay.py")
    copied.append({"file": "check_replay.py", "source": "tools/check_thermal_replay.py", "sha256": sha256(checker)})
    (output / "source-receipt.json").write_text(json.dumps({"manifest_sha256": stage[2], "files": copied,
                                                         "reference_tolerance": {"mse_K2": .02, "temperature_K": .01}}, indent=2) + "\n")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        interpreter = args.python.absolute()
        require(interpreter.is_file(), "Explicit Python interpreter does not exist")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON") and key not in {"VIRTUAL_ENV", "CONDA_PREFIX"}}
        environment.update({"TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
                            "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        probe = subprocess.run([str(interpreter), "-I", "-B", "-c",
            "import json,sys,numpy,scipy,importlib.metadata; print(json.dumps({'python':sys.version,'prefix':sys.prefix,'numpy':numpy.__version__,'scipy':scipy.__version__,'numpy_origin':numpy.__file__,'scipy_origin':scipy.__file__,'packages':{d.metadata['Name'].lower():d.version for d in importlib.metadata.distributions()}}))"],
            env=environment, text=True, capture_output=True, timeout=30, check=False)
        require(probe.returncode == 0, "Interpreter needs explicitly installed NumPy/SciPy; nothing was installed")
        metadata = json.loads(probe.stdout)
        require(metadata["numpy"] == "2.5.3" and metadata["scipy"] == "1.18.1", "Use locked NumPy 2.5.3 / SciPy 1.18.1")
        output = prepare(args.output)
        (output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
        commands = []
        for script in ["check_model.py", "experiment.py", "check_replay.py"]:
            launch_code = "import runpy,sys; root,script=sys.argv[1:3]; sys.path.insert(0,root); sys.argv=[script,*sys.argv[3:]]; runpy.run_path(script,run_name='__main__')"
            command = [str(interpreter), "-I", "-B", "-c", launch_code, str(output), str(output / script)]
            if script == "check_replay.py":
                command += [str(output)]
            result = subprocess.run(command, cwd=output, env=environment, text=True, capture_output=True, timeout=240, check=False)
            (output / f"logs/{script}.stdout.txt").write_text(result.stdout)
            (output / f"logs/{script}.stderr.txt").write_text(result.stderr)
            commands.append({"script": script, "command": command, "returncode": result.returncode})
            (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            require(result.returncode == 0, f"{script} failed; logs retained in {output}")
            print(f"PASS {script}", flush=True)
        print(f"New calculation and verification saved to {output}")
        print("LIMIT: same-platform synthetic thermal task; not hardware validation or full-project reproduction")
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Thermal replay rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
