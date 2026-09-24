"""Explicit-review research workflow; no LLM or experimental/device actuation."""

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from cli import load, new_directory, save
from core import ExperimentBank, add_measurement, card, require, validate_case, validate_records


SCHEMA = "thermal-research-workflow/1"
STAGES = {"pending_review", "no_action", "approved", "rejected", "completed"}
ORIGINS = {"simulated", "user_supplied_research"}


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def model_sources():
    directory = Path(__file__).resolve().parent
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in {
        "core.py": directory / "core.py",
        "radiation/model.py": directory.parent / "radiation/model.py",
    }.items()}


def plan(case, observations):
    bank = ExperimentBank(case)
    recommendation = bank.recommend(observations)
    proposal = {"case": copy.deepcopy(case), "observations": copy.deepcopy(observations),
                "recommendation": recommendation, "model_sources": model_sources()}
    return {
        "schema": SCHEMA, "stage": "pending_review" if recommendation["recommendation"] else "no_action",
        "proposal_id": fingerprint(proposal), "proposal": proposal, "review": None, "outcome": None,
        "engineering_release": "not_supported",
        "events": [{"step": 1, "tool": "ExperimentBank.recommend", "status": recommendation["status"],
                    "planner_solver_calls": bank.solve_calls}],
    }


def validate_session(session):
    require(isinstance(session, dict) and session["schema"] == SCHEMA, "Unsupported workflow schema")
    require(session["stage"] in STAGES, "Unknown workflow stage")
    require(session["engineering_release"] == "not_supported", "Workflow cannot grant engineering release")
    proposal = session["proposal"]
    require(session["proposal_id"] == fingerprint(proposal), "Proposal changed; create and review a new plan")
    require(proposal["model_sources"] == model_sources(), "Model source changed; create and review a new plan")
    validate_case(proposal["case"])
    validate_records(proposal["case"], proposal["observations"])
    require(isinstance(session["events"], list) and bool(session["events"]), "Missing workflow events")
    return proposal


def review(session, proposal_id, experiment, decision, reviewer, acknowledge_research_only):
    proposal = validate_session(session)
    require(session["stage"] == "pending_review", "Only a pending proposal can be reviewed")
    require(proposal_id == session["proposal_id"], "Review refers to a different proposal")
    require(experiment == proposal["recommendation"]["recommendation"], "Review experiment does not match recommendation")
    require(decision in {"approve", "reject"}, "Review decision must be approve or reject")
    require(isinstance(reviewer, str) and 0 < len(reviewer.strip()) <= 120 and reviewer.isprintable(),
            "A printable nonempty reviewer label is required")
    require(acknowledge_research_only is True, "Explicit research-only acknowledgement required; no device authorization")
    updated = copy.deepcopy(session)
    updated["stage"] = "approved" if decision == "approve" else "rejected"
    updated["review"] = {
        "proposal_id": proposal_id, "experiment": experiment, "decision": decision,
        "reviewer": reviewer.strip(), "research_only_acknowledged": True, "identity_verified": False,
    }
    updated["events"].append({"step": len(updated["events"]) + 1, "tool": "declared_review",
                              "status": updated["stage"], "reviewer": reviewer.strip()})
    return updated


def observe(session, measurement, origin):
    proposal = validate_session(session)
    require(session["stage"] == "approved", "Observation requires an approved, unfinished proposal")
    approval = session["review"]
    require(isinstance(approval, dict) and approval["decision"] == "approve"
            and approval["proposal_id"] == session["proposal_id"]
            and approval["research_only_acknowledged"] is True, "Missing or mismatched review record")
    selected = proposal["recommendation"]["recommendation"]
    require(selected is not None and approval["experiment"] == selected
            and measurement["experiment"] == selected, "Observation does not match approved experiment")
    require(origin in ORIGINS, "Observation origin must be explicitly declared")
    case = proposal["case"]
    observations = add_measurement(case, proposal["observations"], measurement)
    bank = ExperimentBank(case)
    posterior, _ = bank.posterior(observations)
    cost = case["experiments"][selected]["cost"]
    updated = copy.deepcopy(session)
    updated["stage"] = "completed"
    updated["outcome"] = {
        "observations": observations, "measurement": copy.deepcopy(measurement),
        "observation_origin": origin, "posterior": posterior,
        "declared_budget": {"before": case["budget"], "spent": cost, "remaining": case["budget"] - cost},
        "engineering_release": "not_supported",
    }
    updated["events"].append({"step": len(updated["events"]) + 1, "tool": "add_measurement",
                              "status": "recorded", "record_id": measurement["id"], "origin": origin})
    updated["events"].append({"step": len(updated["events"]) + 1, "tool": "ExperimentBank.posterior",
                              "status": posterior["status"], "planner_solver_calls": bank.solve_calls})
    return updated


def report(session):
    proposal = session["proposal"]
    lines = ["# 三层协同研究工作流", "", f"流程状态：`{session['stage']}`",
             f"提案标识：`{session['proposal_id']}`", "",
             "A：有限网格信息增益试验选择；B：既有热方程模型；C：确定性工具编排与显式审核。",
             "未调用 LLM、未训练代理模型、未执行真实设备命令。", ""]
    if session["review"]:
        approval = session["review"]
        lines += ["## 审核记录", "", f"自声明审核者：{approval['reviewer']}",
                  f"决定：`{approval['decision']}`；实验：`{approval['experiment']}`。",
                  "身份未认证；仅为研究数据流程审核，不是实际测量发生或设备安全许可的证明。", ""]
    if session["outcome"]:
        outcome = session["outcome"]
        lines += ["## 新观测与更新", "", f"数据来源声明：`{outcome['observation_origin']}`。",
                  f"观测值：{outcome['measurement']['values_K']} K。",
                  f"更新后状态：`{outcome['posterior']['status']}`。",
                  f"候选内相对支持：{json.dumps(outcome['posterior']['model_probability'], ensure_ascii=False)}。",
                  f"本次声明预算：{json.dumps(outcome['declared_budget'], ensure_ascii=False)}。",
                  "完成表示数据已录入，不表示模型可信、候选已穷尽或工程达标。", ""]
    lines += ["## 工具事件", ""]
    lines += [f"- {event['step']}. `{event['tool']}` → `{event['status']}`" for event in session["events"]]
    lines += ["", "## 原始提案", "", card(proposal["recommendation"]),
              "## 工作流边界", "",
              "提案摘要只检测不一致，不是签名或访问控制。预算只记本条结果链的新实验，不是全局账本。",
              "旧审核快照另开输出分支不会被全局去重；操作者必须避免重复记录同一次物理实验。",
              "所有状态 engineering_release=not_supported。", ""]
    return "\n".join(lines)


def write_output(directory, session):
    rendered = report(session)
    new_directory(directory)
    save(directory / "session.json", session)
    (directory / "report.md").write_text(rendered)
    summary = {"stage": session["stage"], "proposal_id": session["proposal_id"],
               "experiment": session["proposal"]["recommendation"]["recommendation"],
               "engineering_release": session["engineering_release"]}
    if session["outcome"]:
        summary["posterior"] = session["outcome"]["posterior"]
        summary["declared_budget"] = session["outcome"]["declared_budget"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="Compute a proposal; stop before review or new observation")
    planning.add_argument("--case", required=True, type=Path)
    planning.add_argument("--observations", required=True, type=Path)
    reviewing = commands.add_parser("review", help="Record explicit approve/reject, without executing experiments")
    reviewing.add_argument("--proposal-id", required=True)
    reviewing.add_argument("--experiment", required=True)
    reviewing.add_argument("--decision", choices=["approve", "reject"], required=True)
    reviewing.add_argument("--reviewer", required=True)
    reviewing.add_argument("--acknowledge-research-only", action="store_true")
    observing = commands.add_parser("observe", help="Append declared research data and update candidate support")
    observing.add_argument("--measurement", required=True, type=Path)
    observing.add_argument("--origin", choices=sorted(ORIGINS), required=True)
    for command in (reviewing, observing):
        command.add_argument("--session", required=True, type=Path)
    for command in (planning, reviewing, observing):
        command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists() and not args.output.is_symlink(), "Output already exists; choose a new directory")
        if args.command == "plan":
            session = plan(load(args.case), load(args.observations))
        elif args.command == "review":
            session = review(load(args.session), args.proposal_id, args.experiment, args.decision,
                             args.reviewer, args.acknowledge_research_only)
        else:
            session = observe(load(args.session), load(args.measurement), args.origin)
        write_output(args.output, session)
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(f"Request rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
