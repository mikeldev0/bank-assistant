"""Reproducible local store benchmark. Synthetic data; not an AIFindr latency claim."""
import json
import platform
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.domain import Proposal, Store  # noqa: E402

with tempfile.TemporaryDirectory() as directory:
    store = Store(str(Path(directory) / "bench.db"))
    samples = []
    for i in range(100):
        start = time.perf_counter()
        a = store.propose("benchmark", Proposal(recipient="Demo User", destination="DEMO-1234",
            amount_cents=100, concept="Synthetic benchmark", idempotency_key=f"benchmark-{i}"))
        store.decide("benchmark", a["id"], a["fingerprint"], True)
        samples.append((time.perf_counter() - start) * 1000)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.decide("benchmark", a["id"], a["fingerprint"], True), range(32)))
    report = {"scope": "Local SQLite proposal + confirmation + simulated execution, excludes HTTP/LLM",
              "python": platform.python_version(), "platform": platform.system(), "samples": len(samples),
              "median_ms": round(statistics.median(samples), 3), "p95_ms": round(sorted(samples)[94], 3),
              "concurrent_confirmation_retries": 32,
              "execution_events_for_retried_action": sum(e["event"] == "executed" for e in store.get("benchmark", a["id"])["audit"])}
    assert report["execution_events_for_retried_action"] == 1, "Repeated confirmation duplicated execution"
    print(json.dumps(report, indent=2))
