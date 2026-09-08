"""Compare complete, controlled, human-reviewed Laboratory runs."""

import argparse
import json
import math
import statistics
from copy import deepcopy

from evaluations.run import capture, digest, review
from evaluations.support import private_path, save


def _validate_evidence(run, row):
    """Re-validate the captured transcript, review and frozen fixture."""
    check = deepcopy(row)
    check["status"] = "todo"
    capture({"project_id": run["project_id"], "cases": []}, check, {**row, "project_id": run["project_id"]})
    review(check, row["review"])
    case = next(c for c in run["dataset"] if c["id"] == row["case_id"])
    fixture = row.get("fixture", {})
    if row["prepared_turns"] != [t.format(**fixture) for t in case["turns"]]:
        raise ValueError("Prepared turns differ from the frozen dataset")
    if case.get("fixture") and fixture.get("observed", {}).get("status") != case["fixture"]["state"]:
        raise ValueError("Missing fixture state evidence")


def validate(run):
    if run.get("schema_version") != 1:
        raise ValueError("Expected versioned manifest; score-only files are insufficient")
    for data, hashed in [
        ("dataset", "dataset_sha256"),
        ("configuration", "config_sha256"),
        ("prompt", "prompt_sha256"),
    ]:
        if digest(run[data]) != run[hashed]:
            raise ValueError("Snapshot hash mismatch")
    ids = [case["id"] for case in run["dataset"]]
    if not 15 <= len(ids) <= 25 or len(ids) != len(set(ids)):
        raise ValueError("Expected 15..25 distinct scenarios")
    if type(run["repeats"]) is not int or not 1 <= run["repeats"] <= 10:
        raise ValueError("Invalid repetition count")
    expected = {(cid, rep) for cid in ids for rep in range(1, run["repeats"] + 1)}
    rows = {(r["case_id"], r["repeat"]): r for r in run["cases"]}
    if len(rows) != len(run["cases"]) or set(rows) != expected:
        raise ValueError("Incomplete or duplicate case/repetition pairs")
    seen = set()
    for row in rows.values():
        if row["status"] != "reviewed":
            raise ValueError("Every case needs captured evidence and human review")
        if row["conversation_id"] in seen:
            raise ValueError("Conversation reused across scenarios")
        seen.add(row["conversation_id"])
        _validate_evidence(run, row)
    return rows


def metrics(run):
    rows = run["cases"]
    action_ids = {c["id"] for c in run["dataset"] if c["category"] != "grounding"}
    action_rows = [r for r in rows if r["case_id"] in action_ids]
    latency = sorted(r["latency_ms"] for r in rows if r["latency_ms"] is not None)
    usage = [r["usage"] for r in rows if r["usage"] is not None]
    return {
        "cases": len(rows),
        "pass_rate": sum(r["review"]["pass"] for r in rows) / len(rows),
        "action_cases": len(action_rows),
        "unsupported_completion_rate": (
            sum(r["review"]["unsupported_completion"] for r in action_rows) / len(action_rows)
            if action_rows
            else None
        ),
        "latency_samples": len(latency),
        "latency_unit": "ms per complete scenario, measured manually",
        "p50_ms": statistics.median(latency) if latency else None,
        "p95_ms": latency[math.ceil(len(latency) * 0.95) - 1] if latency else None,
        "usage_samples": len(usage),
        "tokens": {
            key: {
                "samples": sum(key in u for u in usage),
                "total": sum(u[key] for u in usage if key in u) if any(key in u for u in usage) else None,
            }
            for key in ["input_tokens", "output_tokens"]
        },
    }


def _classify_changes(left, right):
    changes = {"improvements": [], "regressions": [], "persistent_failures": []}
    for pair, old in left.items():
        a, b = old["review"]["pass"], right[pair]["review"]["pass"]
        label = None
        if not a and b:
            label = "improvements"
        elif a and not b:
            label = "regressions"
        elif not b:
            label = "persistent_failures"
        if label:
            changes[label].append({"case_id": pair[0], "repeat": pair[1]})
    return changes


def _select_examples(changes, left, right):
    # Regressions first, then improvements/failures: do not cherry-pick three successes.
    candidates = changes["regressions"] + changes["improvements"] + changes["persistent_failures"]
    examples, selected = [], set()
    for candidate in candidates:
        if candidate["case_id"] in selected:
            continue
        selected.add(candidate["case_id"])
        pair = (candidate["case_id"], candidate["repeat"])
        examples.append({**candidate, "before": left[pair]["review"], "after": right[pair]["review"]})
        if len(examples) == 3:
            break
    return examples


def compare(before, after):
    left, right = validate(before), validate(after)
    if before["phase"] != "baseline" or after["phase"] != "candidate":
        raise ValueError("Compare baseline against candidate, not original snapshots")
    for key in ["project_id", "organization_id", "config_sha256", "dataset_sha256", "repeats"]:
        if before[key] != after[key]:
            raise ValueError(f"Uncontrolled comparison: {key} changed")
    if before["prompt_sha256"] == after["prompt_sha256"]:
        raise ValueError("The candidate prompt is unchanged")
    if {r["conversation_id"] for r in left.values()} & {r["conversation_id"] for r in right.values()}:
        raise ValueError("Before/after must use independent conversations")
    changes = _classify_changes(left, right)
    examples = _select_examples(changes, left, right)
    return {
        "before": metrics(before),
        "after": metrics(after),
        **changes,
        "examples": examples,
        "examples_missing": max(0, 3 - len(examples)),
        "scope": "Human-reviewed Laboratory evidence; no statistical significance or causal proof claimed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--output", required=True, help="Private report destination")
    args = parser.parse_args()
    try:
        report = compare(
            json.loads(private_path(args.before).read_text()),
            json.loads(private_path(args.after).read_text()),
        )
        save(args.output, report)
        print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=2))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(
            1, "Comparison rejected: check reviews, snapshots, independent conversations and phases.\n"
        )


if __name__ == "__main__":
    main()
