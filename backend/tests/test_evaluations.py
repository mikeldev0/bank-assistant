"""Synthetic fixtures test the evaluation machinery, never the real agent's quality."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from evaluations import support
from evaluations.compare import compare, validate
from evaluations.run import capture, digest, review


def scored_run(phase="baseline", repeats=1):
    dataset = [
        {
            "id": f"BA-{i:02}",
            "category": "grounding" if i < 7 else "status",
            "turns": [f"Synthetic question {i}"],
            "success_criterion": "Synthetic fixture",
        }
        for i in range(1, 21)
    ]
    snapshot = {"workflow": "Agent", "model": "test", "allowed_tools": ["test"]}
    run = {
        "schema_version": 1,
        "phase": phase,
        "run_id": phase,
        "repeats": repeats,
        "project_id": "project",
        "organization_id": "org",
        "configuration": snapshot,
        "config_sha256": digest(snapshot),
        "dataset": dataset,
        "dataset_sha256": digest(dataset),
        "prompt": phase,
        "prompt_sha256": digest(phase),
        "cases": [],
    }
    for rep in range(1, repeats + 1):
        for c in dataset:
            row = {"case_id": c["id"], "repeat": rep, "status": "todo", "prepared_turns": c["turns"]}
            capture(
                run,
                row,
                {
                    "project_id": "project",
                    "conversation_id": f"{phase}-{c['id']}-{rep}",
                    "messages": [
                        {"role": "user", "content": c["turns"][0]},
                        {"role": "assistant", "content": "Synthetic pending response"},
                    ],
                    "latency_ms": 100 if rep == 1 else None,
                },
            )
            review(
                row,
                {
                    "pass": True,
                    "unsupported_completion": False,
                    "reviewer": "test",
                    "evidence": "pending",
                    "reason": "synthetic fixture",
                },
            )
            run["cases"].append(row)
    return run


def test_comparison_pairs_repeats_preserves_regressions_and_missing_metrics():
    before, after = scored_run(repeats=3), scored_run("candidate", repeats=3)
    before["cases"][1]["review"]["pass"] = False
    after["cases"][0]["review"]["pass"] = False
    after["cases"][6]["review"]["unsupported_completion"] = True
    result = compare(before, after)
    assert result["regressions"] == [{"case_id": "BA-01", "repeat": 1}]
    assert result["improvements"] == [{"case_id": "BA-02", "repeat": 1}]
    assert result["examples"][0]["case_id"] == "BA-01"
    assert result["examples_missing"] == 1
    assert result["after"]["latency_samples"] == 20
    assert result["after"]["usage_samples"] == 0
    assert result["after"]["tokens"]["input_tokens"]["total"] is None
    assert result["after"]["unsupported_completion_rate"] == 1 / 42


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "unreviewed",
        "conversation",
        "fabricated_quote",
        "prompt_hash",
        "changed_turn",
        "missing_reply",
    ],
)
def test_reject_corrupt_or_incomplete_evidence(mutation):
    run = scored_run()
    row = run["cases"][0]
    if mutation == "missing":
        run["cases"].pop()
    elif mutation == "duplicate":
        run["cases"].append(deepcopy(row))
    elif mutation == "unreviewed":
        row["status"] = "captured"
    elif mutation == "conversation":
        run["cases"][1]["conversation_id"] = row["conversation_id"]
    elif mutation == "fabricated_quote":
        row["review"]["evidence"] = "invented answer"
    elif mutation == "prompt_hash":
        run["prompt"] = "different"
    elif mutation == "changed_turn":
        row["prepared_turns"] = ["different"]
    else:
        row["messages"].pop()
    with pytest.raises(ValueError):
        validate(run)


@pytest.mark.parametrize(
    "field", ["configuration", "project_id", "organization_id", "phase", "same_prompt", "conversation"]
)
def test_comparison_rejects_uncontrolled_changes(field):
    before, after = scored_run(), scored_run("candidate")
    if field == "configuration":
        after[field]["allowed_tools"] = ["extra-tool"]
        after["config_sha256"] = digest(after[field])
    elif field == "same_prompt":
        after["prompt"], after["prompt_sha256"] = before["prompt"], before["prompt_sha256"]
    elif field == "conversation":
        after["cases"][0]["conversation_id"] = before["cases"][0]["conversation_id"]
    else:
        after[field] = "different"
    with pytest.raises(ValueError):
        compare(before, after)


@pytest.mark.parametrize("value", [-1, True, float("nan"), float("inf"), "100"])
def test_capture_rejects_invalid_latency(value):
    run = scored_run()
    row = deepcopy(run["cases"][0])
    row["status"] = "todo"
    with pytest.raises(ValueError):
        capture(
            {"project_id": "project", "cases": []}, row, {**row, "project_id": "project", "latency_ms": value}
        )


def test_private_artifacts_restrict_paths_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(support, "PRIVATE", tmp_path / "private")
    path = tmp_path / "private/report.json"
    support.save(path, {"secret_fixture": "synthetic"})
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {"secret_fixture": "synthetic"}
    with pytest.raises(ValueError):
        support.save(tmp_path / "public.json", {})
    (tmp_path / "private/link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        support.save(tmp_path / "private/link/leak.json", {})


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/mcp",
        "https://user:secret@example.com/mcp",
        "https://example.com/mcp?token=secret",
        "https://example.com/other",
    ],
)
def test_mcp_credentials_cannot_go_over_http_or_url(url):
    with pytest.raises(ValueError):
        support.gateway_url(url)


def test_private_api_contract_and_headers():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-secret"
        assert request.headers["X-Organization-Id"] == "org"
        assert request.url.host == "api-dev.saas.aifindr.ai"
        assert "synthetic-secret" not in str(request.url)
        if request.url.path.endswith("/conversations"):
            assert request.url.params["perPage"] == "1"
            return httpx.Response(200, json={"items": [], "pagination": {"total": 0}})
        return httpx.Response(200, json={"id": "c1", "messages": [{"role": "assistant", "content": "test"}]})

    settings = {
        "AIFINDR_API_KEY": "synthetic-secret",
        "AIFINDR_ORGANIZATION_ID": "org",
        "AIFINDR_PROJECT_ID": "project",
    }
    transport = httpx.MockTransport(respond)
    asyncio.run(support.project_conversations(per_page=1, settings=settings, transport=transport))
    asyncio.run(support.conversation("c1", settings=settings, transport=transport))
    assert [r.url.path for r in calls] == [
        "/api/private/projects/project/conversations",
        "/api/private/conversations/c1",
    ]
    with pytest.raises(ValueError):
        asyncio.run(
            support.conversation(
                "c1",
                settings={**settings, "AIFINDR_API_BASE_URL": "https://untrusted.test"},
                transport=transport,
            )
        )
    assert len(calls) == 2


def test_private_api_does_not_follow_redirects_or_echo_error_bodies():
    def respond(request):
        return httpx.Response(
            302, headers={"Location": "https://untrusted.test"}, text="private server detail"
        )

    settings = {"AIFINDR_API_KEY": "synthetic", "AIFINDR_ORGANIZATION_ID": "org"}
    with pytest.raises(ValueError) as exc:
        asyncio.run(support.conversation("c1", settings=settings, transport=httpx.MockTransport(respond)))
    assert "private server detail" not in str(exc.value)
    assert "302" in str(exc.value)
