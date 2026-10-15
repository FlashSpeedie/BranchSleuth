from __future__ import annotations

PASSING = {"passed"}

TEST_CATEGORIES = ("REGRESSION", "PREEXISTING_FAILURE", "FIXED", "STABLE_PASS", "ADDED_TEST", "REMOVED_TEST", "BASELINE_ONLY", "TARGET_ONLY", "UNKNOWN")

VERIFICATION_CLASSES = (
    "PROVEN_FAILURE",
    "BEHAVIOR_DIVERGENCE",
    "UNVERIFIED_RISK",
    "VERIFIED_CHECK_PASSED",
    "INCONCLUSIVE",
    "BASELINE_FAILURE",
)


def classify_test_pair(baseline: str | None, modified: str | None) -> str:
    b = (baseline or "").lower()
    m = (modified or "").lower()
    if baseline is None and modified is None:
        return "UNKNOWN"
    if baseline is None and modified is not None:
        return "ADDED_TEST" if m in PASSING | {"failed"} else "TARGET_ONLY"
    if baseline is not None and modified is None:
        return "REMOVED_TEST" if b in PASSING | {"failed"} else "BASELINE_ONLY"
    if b in PASSING and m not in PASSING and m:
        return "REGRESSION"
    if b not in PASSING and m in PASSING:
        return "FIXED"
    if b in PASSING and m in PASSING:
        return "STABLE_PASS"
    if b not in PASSING and m not in PASSING:
        return "PREEXISTING_FAILURE"
    return "UNKNOWN"


def classify_probe_result(result: dict) -> tuple[str, str]:
    """Returns (classification, rationale) from a probe execution result dict."""
    status = result.get("status")
    if status == "unsupported":
        return "INCONCLUSIVE", f"probe unsupported: {result.get('reason', 'unspecified')}"
    if status == "environment_error":
        return "INCONCLUSIVE", f"environment failure: {result.get('reason', 'unspecified')}"
    if status == "timeout":
        return "INCONCLUSIVE", "probe exceeded its execution budget"
    if status == "no_divergence":
        if result.get("property_violation"):
            return "PROVEN_FAILURE", result.get("rationale", "property violated on generated input")
        return "VERIFIED_CHECK_PASSED", (
            f"no behavioral divergence detected across {result.get('examples_run', 0)} generated examples"
            + (", stated property held" if result.get("property_checked") else "")
        )
    if status == "divergence_found":
        if result.get("property_violation") and result.get("reproducible"):
            return "PROVEN_FAILURE", result.get(
                "rationale", "explicit property violated and reproduced with the same input"
            )
        if result.get("property_violation"):
            return "PROVEN_FAILURE", result.get("rationale", "explicit property violated")
        if result.get("baseline_exception"):
            return "BASELINE_FAILURE", "baseline itself raised for the discovered input; difference is inconclusive without a stated property"
        return "BEHAVIOR_DIVERGENCE", (
            "baseline and target diverge for the discovered input; no oracle establishes the difference is incorrect"
        )
    if status == "property_violation_found":
        if result.get("reproducible"):
            return "PROVEN_FAILURE", result.get("rationale", "explicit property violated and reproduced")
        return "PROVEN_FAILURE", result.get("rationale", "explicit property violated")
    return "INCONCLUSIVE", f"unrecognized probe status {status!r}"
