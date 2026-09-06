"""Compare human-reviewed AIFindr outputs. No fabricated automatic judge scores."""
import argparse
import json
from pathlib import Path


def load(path):
    rows = json.loads(Path(path).read_text())
    if len(rows) != 20 or len({r["case_id"] for r in rows}) != 20:
        raise ValueError("Expected 20 uniquely identified reviewed cases")
    for row in rows:
        if type(row.get("pass")) is not bool or not row.get("evidence") or not row.get("reason"):
            raise ValueError("Each case needs a boolean pass, evidence and reason")
    return {r["case_id"]: r for r in rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    before, after = load(args.before), load(args.after)
    expected = {case["id"] for case in json.loads(Path(__file__).with_name("cases.json").read_text())}
    if before.keys() != expected or after.keys() != expected:
        raise ValueError("Runs must cover the same fixed evaluation dataset")
    print(json.dumps({"before_pass_rate": sum(r["pass"] for r in before.values()) / 20,
        "after_pass_rate": sum(r["pass"] for r in after.values()) / 20,
        "improvements": [k for k in before if not before[k]["pass"] and after[k]["pass"]],
        "regressions": [k for k in before if before[k]["pass"] and not after[k]["pass"]]}, indent=2))


if __name__ == "__main__":
    main()
