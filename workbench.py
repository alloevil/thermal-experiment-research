"""Read-only entry points for the archived thermal engineering studies."""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent
STAGES = (
    ("feasibility", "数值复现与成本测量", "362b14f3dd0ff0822fcb531617f1aa4f9be89c31079809f557cd6ae1225fd18a", 29),
    ("radiation", "受限加热与非线性辐射", "7e35e852fd126bf18cd40684871390a02373fe9bbbfba3c1011ed8bcccdcce9a", 25),
    ("sensitivity", "参数失配与不可辨识性", "f01a0ad1a930509c416d57c99de4d18d115538e397f83b4a5683c59c9e28fbdd", 204),
    ("calibration", "有效比值校准与留出验证", "c8831a6326e1d24eb5d1ad2112add55e61f351ada0b911b772a96b0565621e2c", 195),
    ("model_mismatch", "未知偏差与残差告警", "7173d1aafd925e6596143164823ef3f17016aef770189a1ed788654e8d532999", 172),
    ("bias_boundary", "小偏置告警盲区", "136c8a2c14787b1423ff9235b2352e08928066713442e54bdf5e219343fefdb1", 248),
    ("reference_correction", "独立参考校正与失效条件", "01baed21bc3979a858f6b207bbf3fa359f15e1562de3862aacd14e18dcb380f5", 303),
    ("evidence_report", "有边界的证据报告", "7f3bc1619cbcc3c1e63e0db67872fd7325a7e911ec40d76341b419cd226b27a5", 10),
)
INTEGRITY_SCOPE = "清单内文件与固定快照一致；未重跑科学实验，不证明真实性、计量溯源或工程安全。"


class SnapshotError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SnapshotError(message)


def file_path(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative, "无效的相对路径")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == relative,
            f"不允许的路径: {relative}")
    current = root
    for component in parsed.parts:
        current = current / component
        require(not current.is_symlink(), f"不允许符号链接: {relative}")
    require(current.is_file(), f"缺少普通文件: {relative}")
    return current


def sha256(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def parse_manifest(payload):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, f"重复JSON键: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise SnapshotError(f"不允许非有限数字: {value}")

    def floating(value):
        number = float(value)
        require(math.isfinite(number), "不允许溢出数字")
        return number

    entries = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid, parse_float=floating)
    require(isinstance(entries, list) and entries, "清单必须是非空列表")
    seen = set()
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {"file", "sha256"}, "清单条目字段错误")
        name, checksum = entry["file"], entry["sha256"]
        require(isinstance(name, str) and name not in seen, "重复或无效的清单路径")
        require(isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum), "无效SHA-256")
        seen.add(name)
    return entries


def check_stage(root, stage):
    name, title, expected, count = stage
    result = {"stage": name, "title": title, "status": "invalid", "verified_artifacts": 0,
              "expected_artifacts": count, "manifest_sha256": expected, "errors": []}
    try:
        manifest = file_path(root, f"{name}/results/artifact-manifest.json")
        payload = manifest.read_bytes()
        require(hashlib.sha256(payload).hexdigest() == expected, "清单摘要与固定pin不一致")
        entries = parse_manifest(payload)
        require(len(entries) == count, "清单条目数量与固定记录不一致")
        for entry in entries:
            try:
                file_path(root / name, entry["file"])
                target = file_path(root, f"{name}/{entry['file']}")
                require(sha256(target) == entry["sha256"], f"文件摘要不匹配: {entry['file']}")
                result["verified_artifacts"] += 1
            except (ValueError, OSError) as error:
                result["errors"].append(str(error))
        if not result["errors"]:
            result["status"] = "matched_snapshot"
    except (ValueError, OSError) as error:
        result["errors"].append(str(error))
    return result


def check_snapshots(root, stages):
    checked = [check_stage(root, stage) for stage in stages]
    return {"schema_version": "thermal-workbench/check/1", "scope": INTEGRITY_SCOPE,
            "status": "matched_snapshot" if all(item["status"] == "matched_snapshot" for item in checked) else "invalid",
            "engineering_release": "not_supported", "stages": checked,
            "verified_artifacts": sum(item["verified_artifacts"] for item in checked)}


def render_check(report):
    lines = [report["scope"]]
    for stage in report["stages"]:
        lines.append(f"{stage['status']}: {stage['stage']} {stage['verified_artifacts']}/{stage['expected_artifacts']}")
        lines.extend(f"  {error}" for error in stage["errors"])
    lines.append(f"整体: {report['status']}；工程放行: not_supported")
    return "\n".join(lines)


def report_command(root, output_format, stages=STAGES):
    checked = check_snapshots(root, stages)
    if checked["status"] != "matched_snapshot":
        print(render_check(checked), file=sys.stderr)
        return 2
    probe = subprocess.run([sys.executable, "-I", "-B", "-c", "import numpy"],
                           capture_output=True, text=True, check=False)
    if probe.returncode:
        print("当前Python不能导入NumPy；请显式使用 feasibility/.venv/bin/python 运行 report。未安装依赖或执行实验。", file=sys.stderr)
        return 2
    reference = next(stage for stage in stages if stage[0] == "reference_correction")
    command = [sys.executable, "-I", "-B", str(root / "evidence_report/report.py"),
               "--stage", str(root / "reference_correction"), "--manifest-sha256", reference[2],
               "--format", output_format]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        print(result.stderr or "证据报告器失败；未输出成功报告。", file=sys.stderr, end="")
        return 2
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    print(result.stdout, end="")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="热工程研究工作台：只读目录、快照检查和证据报告；不自动重算或放行。")
    subcommands = parser.add_subparsers(dest="command", required=True)
    listing = subcommands.add_parser("list", help="列出阶段与阅读入口，不宣称验证通过")
    listing.add_argument("--json", action="store_true")
    check = subcommands.add_parser("check", help="只读核验固定快照；不执行科学实验")
    check.add_argument("stage", nargs="?", default="all", choices=["all"] + [stage[0] for stage in STAGES])
    check.add_argument("--json", action="store_true")
    report = subcommands.add_parser("report", help="先核对全部快照，再生成第七阶段证据说明；需要NumPy")
    report.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            data = {"schema_version": "thermal-workbench/list/1", "status": "not_checked",
                    "stages": [{"stage": name, "title": title, "report": f"{name}/RESULTS.md"}
                               for name, title, _, _ in STAGES],
                    "recompute": "阅读各阶段RUNBOOK.md或RESULTS.md；旧脚本可能写入结果，不由本命令执行。"}
            print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else
                  "目录（未验证）：\n" + "\n".join(f"{item['stage']}: {item['title']} → {item['report']}" for item in data["stages"]))
            return 0
        if args.command == "check":
            selected = STAGES if args.stage == "all" else [stage for stage in STAGES if stage[0] == args.stage]
            data = check_snapshots(ROOT, selected)
            print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else render_check(data))
            return 0 if data["status"] == "matched_snapshot" else 2
        return report_command(ROOT, args.format)
    except (ValueError, OSError, StopIteration) as error:
        print(f"工作台拒绝执行: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
