import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import ExperimentBank, add_measurement, example_case, np, simulate
from workflow import observe, plan, report, review


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = example_case()
        generator = np.random.default_rng(20261001)
        initial = simulate(cls.case["experiments"]["initial"], convection=1.4, cells=96)
        cls.observations = {"records": [{"id": "initial-1", "experiment": "initial",
                                        "values_K": (initial + generator.normal(0, .25, 1)).tolist()}]}
        cls.session = plan(cls.case, cls.observations)
        cls.selected = cls.session["proposal"]["recommendation"]["recommendation"]
        experiment = cls.case["experiments"][cls.selected]
        values = simulate(experiment, convection=1.4, cells=96)
        cls.measurement = {"id": "next-1", "experiment": cls.selected,
                           "values_K": (values + generator.normal(0, .25, len(values))).tolist()}

    def approved(self):
        return review(self.session, self.session["proposal_id"], self.selected, "approve", "test-reviewer", True)

    def test_plan_retains_predictions_and_waits(self):
        self.assertEqual(self.session["stage"], "pending_review")
        self.assertIsNone(self.session["review"])
        self.assertIsNone(self.session["outcome"])
        self.assertEqual(len(self.session["events"]), 1)
        self.assertEqual(self.session["events"][0]["tool"], "ExperimentBank.recommend")
        selected = next(option for option in self.session["proposal"]["recommendation"]["options"]
                        if option["experiment"] == self.selected)
        self.assertEqual(set(selected["predictions"]), {"convection", "offset"})

    def test_unreviewed_observation_is_rejected_before_numeric_tools(self):
        with patch("workflow.ExperimentBank") as bank:
            with self.assertRaisesRegex(ValueError, "approved"):
                observe(self.session, self.measurement, "simulated")
            bank.assert_not_called()

    def test_explicit_review_is_bound_and_has_no_numeric_execution(self):
        before = copy.deepcopy(self.session)
        with patch("workflow.ExperimentBank") as bank, patch("workflow.add_measurement") as append:
            approved = self.approved()
            bank.assert_not_called()
            append.assert_not_called()
        self.assertEqual(self.session, before)
        self.assertEqual(approved["stage"], "approved")
        self.assertFalse(approved["review"]["identity_verified"])
        self.assertIsNone(approved["outcome"])

    def test_review_requires_acknowledgement_matching_proposal_and_experiment(self):
        valid = [self.session, self.session["proposal_id"], self.selected, "approve", "test-reviewer", True]
        for position, value in [(1, "stale-id"), (2, "initial"), (3, "maybe"), (4, " "), (5, False)]:
            with self.subTest(position=position):
                arguments = valid.copy()
                arguments[position] = value
                with self.assertRaises(ValueError):
                    review(*arguments)

    def test_modified_proposal_requires_replanning(self):
        for target in ["budget", "observations", "recommendation"]:
            modified = copy.deepcopy(self.session)
            if target == "budget":
                modified["proposal"]["case"]["budget"] = 10
            elif target == "observations":
                modified["proposal"]["observations"]["records"][0]["values_K"][0] += .1
            else:
                modified["proposal"]["recommendation"]["recommendation"] = "cooldown"
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Proposal changed"):
                review(modified, modified["proposal_id"], self.selected, "approve", "test", True)

    def test_changed_model_source_requires_replanning(self):
        with patch("workflow.model_sources", return_value={"core.py": "changed"}):
            with self.assertRaisesRegex(ValueError, "Model source changed"):
                self.approved()

    def test_rejection_is_terminal(self):
        rejected = review(self.session, self.session["proposal_id"], self.selected, "reject", "test", True)
        self.assertEqual(rejected["stage"], "rejected")
        with self.assertRaises(ValueError):
            observe(rejected, self.measurement, "simulated")
        with self.assertRaises(ValueError):
            review(rejected, rejected["proposal_id"], self.selected, "approve", "test", True)

    def test_approval_record_cannot_be_missing_or_mismatched(self):
        for value in [None, {"decision": "reject"}, {"decision": "approve", "proposal_id": "wrong"}]:
            approved = self.approved()
            approved["review"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                observe(approved, self.measurement, "simulated")

    def test_wrong_experiment_duplicate_record_and_nonfinite_data_rejected(self):
        for changes in [{"experiment": "initial", "values_K": [300.]}, {"id": "initial-1"},
                        {"values_K": [float("nan")] * len(self.measurement["values_K"])},
                        {"values_K": []}]:
            measurement = dict(self.measurement, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                observe(self.approved(), measurement, "simulated")

    def test_observation_origin_is_required(self):
        with self.assertRaisesRegex(ValueError, "origin"):
            observe(self.approved(), self.measurement, "verified_real_device")

    def test_update_matches_original_math_and_preserves_inputs(self):
        approved = self.approved()
        before = copy.deepcopy(approved)
        completed = observe(approved, self.measurement, "simulated")
        expected_data = add_measurement(self.case, self.observations, self.measurement)
        expected, _ = ExperimentBank(self.case).posterior(expected_data)
        self.assertEqual(completed["outcome"]["posterior"], expected)
        self.assertEqual(completed["outcome"]["observations"], expected_data)
        self.assertEqual(completed["outcome"]["declared_budget"], {"before": 1, "spent": 1, "remaining": 0})
        self.assertEqual(completed["stage"], "completed")
        self.assertEqual(completed["engineering_release"], "not_supported")
        self.assertEqual(approved, before)
        with self.assertRaises(ValueError):
            observe(completed, self.measurement, "simulated")
        self.assertIn("数据来源声明：`simulated`", report(completed))

    def test_candidate_failure_is_retained_and_still_costs_an_experiment(self):
        measurement = dict(self.measurement, values_K=[400.] * len(self.measurement["values_K"]))
        completed = observe(self.approved(), measurement, "simulated")
        self.assertEqual(completed["outcome"]["posterior"]["status"], "unsupported")
        self.assertEqual(completed["outcome"]["declared_budget"]["spent"], 1)
        self.assertEqual(completed["outcome"]["posterior"]["engineering_release"], "not_supported")

    def test_equivalent_outside_budget_and_temperature_cases_do_not_request_review(self):
        case = example_case()
        case["grid"] = {"convection": [1], "offset_K": [0], "gain": [1], "capacity": [1]}
        observations = {"records": [{"id": "initial", "experiment": "initial",
                                    "values_K": simulate(case["experiments"]["initial"]).tolist()}]}
        variants = [(case, observations, "not_distinguishable")]
        variants.append((copy.deepcopy(case), observations, "no_available_experiment"))
        variants[-1][0]["budget"] = .5
        variants.append((copy.deepcopy(case), observations, "no_available_experiment"))
        variants[-1][0]["max_predicted_temperature_K"] = 296.15
        variants.append((case, {"records": [{"id": "outside", "experiment": "initial", "values_K": [400.]}]}, "unsupported"))
        for candidate, records, status in variants:
            with self.subTest(status=status):
                session = plan(candidate, records)
                self.assertEqual(session["stage"], "no_action")
                self.assertEqual(session["proposal"]["recommendation"]["status"], status)
                with self.assertRaises(ValueError):
                    review(session, session["proposal_id"], "heat_high", "approve", "test", True)

    def test_cli_resumes_across_processes_and_refuses_overwrite(self):
        executable = Path(__file__).resolve().with_name("workflow.py")
        with tempfile.TemporaryDirectory(prefix="thermal workflow ") as directory:
            root = Path(directory)
            for name, value in [("case", self.case), ("observations", self.observations), ("measurement", self.measurement)]:
                (root / f"{name}.json").write_text(json.dumps(value))

            def run(*arguments):
                return subprocess.run([sys.executable, "-B", str(executable), *map(str, arguments)],
                                      cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TZ="UTC"),
                                      capture_output=True, text=True, timeout=120)

            planned = run("plan", "--case", "case.json", "--observations", "observations.json", "--output", "计划")
            self.assertEqual(planned.returncode, 0, planned.stderr)
            plan_file = root / "计划/session.json"
            saved = plan_file.read_bytes()
            session = json.loads(saved)
            rejected = run("observe", "--session", plan_file, "--measurement", "measurement.json",
                           "--origin", "simulated", "--output", "unreviewed")
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse((root / "unreviewed").exists())
            approved = run("review", "--session", plan_file, "--proposal-id", session["proposal_id"],
                           "--experiment", self.selected, "--decision", "approve", "--reviewer", "simulation-review",
                           "--acknowledge-research-only", "--output", "审核")
            self.assertEqual(approved.returncode, 0, approved.stderr)
            completed = run("observe", "--session", root / "审核/session.json", "--measurement", "measurement.json",
                            "--origin", "simulated", "--output", "结果")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["stage"], "completed")
            self.assertEqual(plan_file.read_bytes(), saved)
            overwritten = run("plan", "--case", "case.json", "--observations", "observations.json", "--output", "结果")
            self.assertEqual(overwritten.returncode, 2)

    def test_demo_without_optin_stops_before_new_observation(self):
        executable = Path(__file__).resolve().with_name("demo_workflow.py")
        with tempfile.TemporaryDirectory(prefix="thermal paused demo ") as directory:
            output = Path(directory) / "paused"
            process = subprocess.run([sys.executable, "-B", str(executable), "--output", str(output)],
                                     env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TZ="UTC"),
                                     capture_output=True, text=True, timeout=120)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["stage"], "pending_review")
            self.assertFalse(result["simulation_opt_in"])
            self.assertFalse((output / "measurement.json").exists())
            self.assertFalse((output / "review").exists())
            self.assertFalse((output / "completed").exists())
            self.assertNotIn("simulation-truth.json", (output / "commands.log").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
