"""Internal consistency only: recorded judge outcomes are not re-evaluated here."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_grounding_csv_matches_json_and_case_ids_are_unique():
    cases = json.loads((ROOT / "evaluations/grounding-cases.json").read_text())
    with (ROOT / "evaluations/grounding-cases.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(cases) == len(rows) == 20
    assert len({case["id"] for case in cases}) == len(cases)
    for case, row in zip(cases, rows, strict=True):
        assert json.loads(row["messages"]) == case["messages"]
        assert row["criteria"] == case["criteria"]


def test_report_totals_match_every_recorded_case():
    cases = json.loads((ROOT / "evaluations/grounding-cases.json").read_text())
    expected_ids = {case["id"] for case in cases}
    report = json.loads((ROOT / "evaluations/results/2026-09-08-grounding.json").read_text())
    for name in ["control", "variant_b", "control_verification", "variant_b_v2"]:
        run = report[name]
        assert len(run["cases"]) == run["count"] == len(expected_ids)
        assert {case["case_id"] for case in run["cases"]} == expected_ids
        assert all(type(case["judge_passed"]) is bool for case in run["cases"])
        assert sum(case["judge_passed"] for case in run["cases"]) == run["passed"]
        assert sum(case["tool_calls"] for case in run["cases"]) == run["total_tool_calls"]
        assert sum(case["tokens_total_displayed"] for case in run["cases"]) == run["tokens_total_displayed_sum"]
