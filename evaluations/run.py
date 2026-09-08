"""Prepare in Laboratory, capture evidence, then review. No invented agent responses."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import math
from uuid import uuid4

from evaluations.support import (
    PRIVATE,
    ROOT,
    call,
    config,
    conversation,
    gateway,
    now,
    private_path,
    project_conversations,
    save,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def new_run(name, phase, prompt, configuration, repeats):
    if not name or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name
    ):
        raise ValueError("Run name must contain only letters, numbers, - or _")
    if not 1 <= repeats <= 10:
        raise ValueError("Repeats must be 1..10")
    prompt_text = private_path(prompt).read_text()
    if not prompt_text.strip():
        raise ValueError("Capture the actual published prompt first")
    snapshot = json.loads(private_path(configuration).read_text())
    required = {"workflow", "model", "knowledge_base_revision", "allowed_tools", "parameters", "mcp_revision"}
    if not required <= snapshot.keys() or snapshot["workflow"] != "Agent":
        raise ValueError(
            "Config needs Agent workflow, model, knowledge_base_revision, allowed_tools, parameters, mcp_revision"
        )
    if not all(snapshot[k] for k in ["model", "knowledge_base_revision", "mcp_revision"]):
        raise ValueError("Config revisions and model must be non-empty")
    if not isinstance(snapshot["parameters"], dict) or not isinstance(snapshot["allowed_tools"], list):
        raise TypeError("Parameters must be an object and allowed_tools a list")
    settings = config()
    if not settings.get("AIFINDR_PROJECT_ID") or not settings.get("AIFINDR_ORGANIZATION_ID"):
        raise ValueError("Set project and organization IDs in root .env")
    dataset = json.loads((ROOT / "evaluations/cases.json").read_text())
    run = {
        "schema_version": 1,
        "run_id": name,
        "phase": phase,
        "created_at": now(),
        "project_id": settings["AIFINDR_PROJECT_ID"],
        "organization_id": settings["AIFINDR_ORGANIZATION_ID"],
        "prompt_sha256": digest(prompt_text),
        "config_sha256": digest(snapshot),
        "dataset_sha256": digest(dataset),
        "configuration": snapshot,
        "dataset": dataset,
        "prompt": prompt_text,
        "repeats": repeats,
        "cases": [
            {"case_id": case["id"], "repeat": repeat, "status": "todo"}
            for repeat in range(1, repeats + 1)
            for case in dataset
        ],
    }
    directory = private_path(PRIVATE / "evaluations" / name)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(directory / "run.json", run)
    return directory / "run.json"


def case_row(run, case_id, repeat):
    return next(row for row in run["cases"] if row["case_id"] == case_id and row["repeat"] == repeat)


async def prepare(run, row, url):
    if row["status"] != "todo":
        raise ValueError("Case is already captured; create a new run to repeat it")
    case = next(c for c in run["dataset"] if c["id"] == row["case_id"])
    fixture = case.get("fixture")
    if fixture:
        # Stable across retries, different across runs/cases/repetitions.
        key = digest([run["run_id"], row["case_id"], row["repeat"]])
        async with gateway(url) as session:
            if not row.get("fixture"):
                proposed = await call(
                    session,
                    "propose_transfer",
                    {
                        "recipient": "Alex Demo",
                        "destination": "DEMO-4821",
                        "amount_cents": 12500,
                        "concept": "Evaluación sintética",
                        "idempotency_key": key,
                    },
                )
                row["fixture"] = {"action_id": proposed["id"], "idempotency_key": key}
            state = await call(session, "get_transfer_status", {"action_id": row["fixture"]["action_id"]})
        row["fixture"]["observed"] = state
        row["fixture"]["observed_at"] = now()
        row["fixture"]["ready"] = state["status"] == fixture["state"]
        if not row["fixture"]["ready"]:
            return {
                "ready": False,
                "action_id": state["id"],
                "current_state": state["status"],
                "required_state": fixture["state"],
                "instruction": fixture["instruction"],
            }
    substitutions = row.get("fixture", {})
    turns = [turn.format(**substitutions) for turn in case["turns"]]
    row["prepared_turns"] = turns
    row["prepared_at"] = now()
    return {
        "ready": True,
        "instruction": "Open a fresh conversation in the assigned project's Laboratory. "
        "Send these turns sequentially in the SAME conversation; save its ID and full transcript.",
        "turns": turns,
        "success_criterion": case["success_criterion"],
    }


def _validate_transcript(messages, prepared_turns):
    """Require valid messages and an answer to every prepared user turn."""
    if not messages or any(
        m.get("role") not in {"user", "assistant", "tool", "system"}
        or not isinstance(m.get("content"), str)
        or not m["content"].strip()
        for m in messages
    ):
        raise ValueError("Messages need a valid role and non-empty text content")
    if [m["content"] for m in messages if m["role"] == "user"] != prepared_turns:
        raise ValueError("User turns must exactly match the prepared scenario in order")
    awaiting_answer = False
    for message in messages:
        if message["role"] == "user":
            if awaiting_answer:
                raise ValueError("Each user turn needs an assistant response")
            awaiting_answer = True
        elif message["role"] == "assistant":
            awaiting_answer = False
    if awaiting_answer:
        raise ValueError("Transcript ends before the last assistant response")


def _validate_measurements(evidence):
    """Accept only measured, finite latency and nonnegative token counts."""
    latency = evidence.get("latency_ms")
    if latency is not None and (
        type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0
    ):
        raise ValueError("latency_ms must be a nonnegative measured number or null")
    usage = evidence.get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or not usage or not set(usage) <= {"input_tokens", "output_tokens"}:
            raise ValueError("usage needs input_tokens and/or output_tokens; omit unavailable data")
        if any(type(v) is not int or v < 0 for v in usage.values()):
            raise ValueError("Token counts must be nonnegative integers")
    return latency, usage


def capture(run, row, evidence):
    if row["status"] != "todo" or not row.get("prepared_turns"):
        raise ValueError("Prepare the case first; existing evidence cannot be overwritten")
    if row.get("fixture") and not row["fixture"].get("ready"):
        raise ValueError("Fixture is not in its required state")
    if evidence.get("project_id") != run["project_id"]:
        raise ValueError("Evidence must identify the assigned project")
    cid = evidence.get("conversation_id")
    if (
        not isinstance(cid, str)
        or not cid.strip()
        or any(r.get("conversation_id") == cid for r in run["cases"])
    ):
        raise ValueError("Use a unique non-empty conversation ID per case and repetition")
    messages = evidence.get("messages", [])
    _validate_transcript(messages, row["prepared_turns"])
    latency, usage = _validate_measurements(evidence)
    row.update(
        {
            "status": "captured",
            "conversation_id": cid,
            "messages": messages,
            "captured_at": now(),
            "latency_ms": latency,
            "usage": usage,
            "source": "manual_laboratory",
            "review": None,
        }
    )


def review(row, score):
    if row["status"] != "captured":
        raise ValueError("Capture evidence before reviewing; reviews cannot be overwritten")
    if any(type(score.get(k)) is not bool for k in ["pass", "unsupported_completion"]):
        raise ValueError("Review needs boolean pass and unsupported_completion")
    if not all(
        isinstance(score.get(k), str) and score[k].strip() for k in ["reviewer", "reason", "evidence"]
    ):
        raise ValueError("Review needs reviewer, reason, and an exact assistant evidence quote")
    if not any(score["evidence"] in m["content"] for m in row["messages"] if m["role"] == "assistant"):
        raise ValueError("Review evidence must be an exact quote from an assistant response")
    row["review"] = {**score, "reviewed_at": now()}
    row["status"] = "reviewed"


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    create = subs.add_parser("create")
    create.add_argument("name")
    create.add_argument("--phase", choices=["original", "baseline", "candidate"], required=True)
    create.add_argument("--prompt", required=True)
    create.add_argument("--config", required=True)
    create.add_argument("--repeats", type=int, default=1)
    for command in ["prepare", "capture", "review", "fetch"]:
        sub = subs.add_parser(command)
        sub.add_argument("run")
        sub.add_argument("case_id")
        sub.add_argument("--repeat", type=int, default=1)
        if command == "prepare":
            sub.add_argument("--mcp-url", default="http://127.0.0.1:8000/mcp")
        elif command == "fetch":
            sub.add_argument("conversation_id")
            sub.add_argument(
                "--project-page",
                type=int,
                default=1,
                help="Page of 100 project conversations containing this ID",
            )
        else:
            sub.add_argument("file")
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "create":
            print(new_run(args.name, args.phase, args.prompt, args.config, args.repeats))
            return
        path = private_path(args.run)
        with path.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            run = json.loads(path.read_text())
            row = case_row(run, args.case_id, args.repeat)
            if args.command == "prepare":
                result = asyncio.run(prepare(run, row, args.mcp_url))
            elif args.command == "fetch":
                settings = config()
                if any(
                    settings.get(key) != run[field]
                    for key, field in [
                        ("AIFINDR_PROJECT_ID", "project_id"),
                        ("AIFINDR_ORGANIZATION_ID", "organization_id"),
                    ]
                ):
                    raise ValueError("Current credentials target a different project or organization")
                page = asyncio.run(project_conversations(page=args.project_page, per_page=100))
                if not any(item.get("id") == args.conversation_id for item in page["items"]):
                    raise ValueError("Conversation not found on this project page")
                raw = asyncio.run(conversation(args.conversation_id))
                dest = path.parent / f"raw-{args.case_id}-{args.repeat}-{uuid4().hex}.json"
                save(dest, raw)
                capture(
                    run,
                    row,
                    {
                        "project_id": run["project_id"],
                        "conversation_id": raw["id"],
                        "messages": raw["messages"],
                    },
                )
                row.update({"source": "private_api", "raw_sha256": digest(raw), "raw_file": str(dest)})
                result = {
                    "saved": str(dest),
                    "status": row["status"],
                    "instruction": "Transcript captured from DEV. Human scoring is still required.",
                }
            else:
                data = json.loads(private_path(args.file).read_text())
                if args.command == "capture":
                    capture(run, row, data)
                else:
                    review(row, data)
                result = {"status": row["status"], "case_id": row["case_id"]}
            save(path, run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 -- CLI boundary deliberately redacts third-party exception bodies.
        # Do not echo upstream bodies, filesystem input or credentials in terminal errors.
        parser.exit(
            1, "Operation failed: check inputs, case state, and private configuration. No secrets logged.\n"
        )


if __name__ == "__main__":
    main()
