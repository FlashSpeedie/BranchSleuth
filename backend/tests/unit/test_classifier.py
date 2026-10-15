from app.services.classifier import classify_probe_result, classify_test_pair


def test_categories_matrix():
    assert classify_test_pair("passed", "passed") == "STABLE_PASS"
    assert classify_test_pair("passed", "failed") == "REGRESSION"
    assert classify_test_pair("failed", "failed") == "PREEXISTING_FAILURE"
    assert classify_test_pair("failed", "passed") == "FIXED"
    assert classify_test_pair(None, "passed") in ("ADDED_TEST", "TARGET_ONLY")
    assert classify_test_pair("passed", None) in ("REMOVED_TEST", "BASELINE_ONLY")
    assert classify_test_pair("passed", "error") == "REGRESSION"
    assert classify_test_pair("skipped", "skipped") == "PREEXISTING_FAILURE"
    assert classify_test_pair(None, None) == "UNKNOWN"


def test_probe_unsupported_is_inconclusive():
    classification, rationale = classify_probe_result({"status": "unsupported", "reason": "async function"})
    assert classification == "INCONCLUSIVE"
    assert "async" in rationale


def test_probe_timeout_inconclusive():
    classification, _ = classify_probe_result({"status": "timeout"})
    assert classification == "INCONCLUSIVE"


def test_probe_property_violation_reproducible_is_proven():
    classification, rationale = classify_probe_result(
        {"status": "property_violation_found", "property_violation": True, "reproducible": True}
    )
    assert classification == "PROVEN_FAILURE"
    assert "reproduced" in rationale or "reproduced" in rationale.lower() or "property" in rationale


def test_probe_divergence_without_oracle_is_not_proven():
    classification, rationale = classify_probe_result(
        {"status": "divergence_found", "baseline_exception": False, "examples_run": 40}
    )
    assert classification == "BEHAVIOR_DIVERGENCE"
    assert "no oracle" in rationale


def test_probe_baseline_exception_is_baseline_failure():
    classification, rationale = classify_probe_result(
        {"status": "divergence_found", "baseline_exception": True, "reproducible": True}
    )
    assert classification == "BASELINE_FAILURE"


def test_probe_no_divergence_with_property_passed():
    classification, rationale = classify_probe_result(
        {"status": "no_divergence", "property_checked": True, "examples_run": 50}
    )
    assert classification == "VERIFIED_CHECK_PASSED"
    assert "50" in rationale


def test_probe_environment_error_inconclusive():
    classification, _ = classify_probe_result({"status": "environment_error", "reason": "import failed"})
    assert classification == "INCONCLUSIVE"


def test_probe_unknown_status_inconclusive():
    classification, _ = classify_probe_result({"status": "weird"})
    assert classification == "INCONCLUSIVE"
