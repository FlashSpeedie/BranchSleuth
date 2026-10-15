import json

RESULTS: list[dict] = []
COLLECTED = 0
OUT = "/bs/out/test_results.json"
MAX_EXCERPT = 2000


def _sanitize(text: str) -> str:
    for prefix in ("/bs/baseline/", "/bs/modified/", "/bs/src/"):
        text = text.replace(prefix, "")
    return text[:MAX_EXCERPT]


def pytest_sessionstart(session):
    global COLLECTED
    COLLECTED = 0


def pytest_collection_finish(session):
    global COLLECTED
    COLLECTED = len(session.items)


def pytest_runtest_logreport(report):
    if report.when == "call":
        outcome = report.outcome
    elif report.when == "setup" and report.outcome in ("failed", "skipped"):
        outcome = "error" if report.outcome == "failed" else "skipped"
    elif report.when == "teardown" and report.outcome == "failed":
        outcome = "error"
    else:
        return
    if report.when == "call" and hasattr(report, "wasxfail"):
        outcome = "xfailed"
    excerpt = None
    if outcome in ("failed", "error") and report.longrepr is not None:
        excerpt = _sanitize(str(report.longreprtext if hasattr(report, "longreprtext") else report.longrepr))
    if report.when == "call":
        RESULTS[-1].update(
            {
                "outcome": outcome,
                "duration": getattr(report, "duration", 0.0),
                "error_excerpt": excerpt,
            }
        )
    else:
        RESULTS.append(
            {
                "node_id": report.nodeid,
                "name": report.nodeid.split("::")[-1],
                "outcome": outcome,
                "duration": getattr(report, "duration", 0.0),
                "error_excerpt": excerpt,
            }
        )


def pytest_runtest_logstart(nodeid, location):
    RESULTS.append({"node_id": nodeid, "name": nodeid.split("::")[-1], "outcome": "passed", "duration": 0.0, "error_excerpt": None})


def pytest_sessionfinish(session, exitstatus):
    seen = {}
    for r in RESULTS:
        prev = seen.get(r["node_id"])
        if prev is None:
            seen[r["node_id"]] = r
            continue
        rank = {"failed": 0, "error": 1, "skipped": 2, "xfailed": 3, "passed": 4}
        if rank.get(r["outcome"], 5) < rank.get(prev["outcome"], 5):
            seen[r["node_id"]] = r
    payload = {"tests": list(seen.values()), "collected": COLLECTED, "exit_status": int(exitstatus)}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    import os

    os.replace(tmp, OUT)
