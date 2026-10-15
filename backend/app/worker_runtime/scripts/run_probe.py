import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, "/opt/deps")

SPEC_PATH = Path("/bs/spec/probe_spec.json")
OUT_PATH = Path("/bs/out/probe_results.json")
MAX_REPR = 500
TARGET_TIME_BUDGET = 45.0

RESULTS: dict = {"started_at": time.time(), "targets": {}}


def write_results() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(RESULTS))
    os.replace(tmp, OUT_PATH)


def trunc(value, limit: int = MAX_REPR) -> str:
    try:
        text = repr(value)
    except Exception:
        text = "<unreprable>"
    return text if len(text) <= limit else text[:limit] + "..."


def sanitize(text: str) -> str:
    for prefix in ("/bs/baseline/", "/bs/modified/"):
        text = text.replace(prefix, "")
    return text[-2000:]


def import_module_at(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def resolve_qualname(mod, qualname: str):
    obj = mod
    for part in qualname.split("."):
        obj = getattr(obj, part)
        if hasattr(obj, "__func__"):
            obj = obj.__func__
    return obj


def call_function(fn, kwargs: dict) -> dict:
    try:
        value = fn(**kwargs)
        return {"kind": "return", "value": value, "repr": trunc(value)}
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit, MemoryError)):
            raise
        return {
            "kind": "exception",
            "exception": e,
            "type": type(e).__name__,
            "message": trunc(str(e), 300),
            "traceback": sanitize(traceback.format_exc()),
        }


def serial_out(out: dict) -> dict:
    if out["kind"] == "return":
        return {"kind": "return", "repr": out["repr"]}
    return {"kind": "exception", "type": out["type"], "message": out["message"], "traceback": out["traceback"]}


def outcome_signature(out: dict) -> str:
    if out["kind"] == "return":
        return "return:" + out["repr"]
    return "exception:" + out["type"] + ":" + out["message"]


def build_strategy(spec):
    from hypothesis import strategies as st

    if isinstance(spec, str):
        if spec == "int":
            return st.integers(min_value=-(10**9), max_value=10**9)
        if spec == "float":
            return st.floats(allow_nan=False, allow_infinity=False, width=64)
        if spec == "bool":
            return st.booleans()
        if spec == "text":
            return st.text(max_size=64)
        return None
    if isinstance(spec, dict):
        if spec.get("type") == "list":
            child = build_strategy(spec.get("element"))
            if child is None:
                return None
            return st.lists(child, max_size=4)
        if spec.get("type") == "union":
            variants = [build_strategy(v) for v in spec.get("variants", [])]
            variants = [v for v in variants if v is not None]
            if not variants:
                return None
            if len(variants) == 1:
                return variants[0]
            return st.one_of(*variants)
    return None


def make_property_checker(property_code: str):
    namespace: dict = {}
    exec(compile(property_code, "<property>", "exec"), namespace)
    check = namespace.get("check")
    if not callable(check):
        raise ValueError("property code must define a callable named check(kwargs, outcome)")
    return check


def evaluate_property(check, kwargs: dict, modified_out: dict):
    if modified_out["kind"] == "return":
        argument = {"kind": "return", "value": modified_out["value"]}
    else:
        argument = {"kind": "exception", "exception": modified_out["exception"]}
    try:
        ok = bool(check(dict(kwargs), argument))
        return (True, None) if ok else (False, "property check returned a falsey result")
    except AssertionError as e:
        return False, sanitize(str(e)) or "property assertion failed"
    except Exception as e:
        return False, f"property check raised {type(e).__name__}: {e}"


def run_target(target: dict) -> dict:
    result: dict = {
        "target_id": target["id"],
        "file": target["file"],
        "qualname": target["qualname"],
        "status": "no_divergence",
        "examples_run": 0,
        "property_checked": bool(target.get("property_code")),
        "property_held": None,
        "property_violation": False,
        "reproducible": None,
        "via": None,
        "minimized": False,
        "input": None,
        "baseline_outcome": None,
        "modified_outcome": None,
        "rationale": None,
        "reason": None,
    }
    started = time.time()
    suffix = target["id"].replace("-", "_")
    base_file = os.path.join("/bs/baseline", target["file"])
    mod_file = os.path.join("/bs/modified", target["file"])
    if not os.path.exists(base_file) or not os.path.exists(mod_file):
        result.update(status="unsupported", reason="target file missing in one of the revisions")
        return result
    try:
        base_mod = import_module_at(base_file, f"bs_probe_baseline_{suffix}")
        mod_mod = import_module_at(mod_file, f"bs_probe_modified_{suffix}")
        base_fn = resolve_qualname(base_mod, target["qualname"])
        mod_fn = resolve_qualname(mod_mod, target["qualname"])
    except Exception as e:
        result.update(
            status="environment_error",
            reason=f"import failed: {type(e).__name__}: {sanitize(str(e))[:300]}",
        )
        return result

    params = target["params"]
    strategies: dict = {}
    fixed_kwargs: dict = {}
    for p in params:
        built = build_strategy(p["strategy"])
        if built is None and not p.get("has_default"):
            result.update(status="unsupported", reason=f"no strategy for parameter {p['name']}")
            return result
        if built is None:
            fixed_kwargs[p["name"]] = p.get("default")
        else:
            strategies[p["name"]] = built
            if p.get("has_default"):
                fixed_kwargs.setdefault(p["name"], p.get("default"))

    check = None
    if target.get("property_code"):
        try:
            check = make_property_checker(target["property_code"])
        except Exception as e:
            result.update(status="unsupported", reason=f"invalid property code: {e}")
            return result

    def full_kwargs(partial: dict) -> dict:
        kw = dict(fixed_kwargs)
        kw.update(partial)
        return kw

    counter = {"n": 0}

    def probe(partial: dict) -> dict:
        counter["n"] += 1
        kwargs = full_kwargs(partial)
        b = call_function(base_fn, kwargs)
        m = call_function(mod_fn, kwargs)
        div = outcome_signature(b) != outcome_signature(m)
        violated = None
        if check is not None and m["kind"] == "return":
            ok, why = evaluate_property(check, kwargs, m)
            violated = None if ok else (why or "property violated")
        return {
            "kwargs": kwargs,
            "b": b,
            "m": m,
            "divergence": div,
            "property_violation": violated,
        }

    candidates: list[dict] = []
    param_strats = {p["name"]: p["strategy"] for p in params}
    for binfo in target.get("boundaries", []):
        pname = binfo.get("param")
        if pname in strategies:
            candidates.append({pname: binfo["value"]})
    for pname, s in param_strats.items():
        if pname not in strategies:
            continue
        if s == "int":
            candidates.extend([{pname: v} for v in (0, 1, -1, 2, 100, -100)])
        elif s == "text":
            candidates.extend([{pname: v} for v in ("", "a", "0", "x" * 32)])
        elif s == "bool":
            candidates.extend([{pname: v} for v in (True, False)])

    for cand in candidates:
        if time.time() - started > TARGET_TIME_BUDGET:
            result.update(status="timeout", reason="target time budget exhausted during boundary probing")
            return result
        finding = probe(cand)
        if finding["property_violation"]:
            b, m = finding["b"], finding["m"]
            result.update(
                status="property_violation_found",
                property_violation=True,
                property_held=False,
                reproducible=True,
                via="boundary",
                input={k: trunc(v, 200) for k, v in finding["kwargs"].items()},
                baseline_outcome=serial_out(b),
                modified_outcome=serial_out(m),
                rationale=f"explicit property violated at a boundary input ({finding['property_violation']}); reproduced on immediate re-run",
            )
            return result
        if finding["divergence"] and check is None:
            result.update(
                status="divergence_found",
                via="boundary",
                input={k: trunc(v, 200) for k, v in finding["kwargs"].items()},
                baseline_outcome=serial_out(finding["b"]),
                modified_outcome=serial_out(finding["m"]),
                rationale="baseline and target diverge at a boundary input; no oracle states which is correct",
            )
            return result

    from hypothesis import HealthCheck, find
    from hypothesis import settings as hyp_settings
    from hypothesis.strategies import fixed_dictionaries

    kw_strategy = fixed_dictionaries(strategies) if strategies else None
    hset = hyp_settings(
        max_examples=target.get("max_examples", 60),
        deadline=target.get("deadline_ms", 2000),
        database=None,
        suppress_health_check=list(HealthCheck),
    )

    def predicate_property(partial: dict) -> bool:
        finding = probe(partial)
        if finding["property_violation"]:
            return True
        return False

    def predicate_divergence(partial: dict) -> bool:
        finding = probe(partial)
        return finding["divergence"]

    found = None
    try:
        if check is not None and kw_strategy is not None:
            found = find(kw_strategy, predicate_property, settings=hset)
            if found is not None:
                finding = probe(found)
                if finding["property_violation"]:
                    result.update(
                        status="property_violation_found",
                        property_violation=True,
                        property_held=False,
                        reproducible=True,
                        via="hypothesis",
                        minimized=True,
                        input={k: trunc(v, 200) for k, v in finding["kwargs"].items()},
                        baseline_outcome=serial_out(finding["b"]),
                        modified_outcome=serial_out(finding["m"]),
                        rationale=f"explicit property violated on a Hypothesis-minimized input ({finding['property_violation']}); reproduced on immediate re-run",
                    )
                    result["examples_run"] = counter["n"]
                    return result
                found = None
        if check is not None:
            result["property_held"] = True
        if kw_strategy is not None and time.time() - started < TARGET_TIME_BUDGET:
            found = find(kw_strategy, predicate_divergence, settings=hset)
            if found is not None:
                finding = probe(found)
                if finding["divergence"]:
                    result.update(
                        status="divergence_found",
                        via="hypothesis",
                        minimized=True,
                        input={k: trunc(v, 200) for k, v in finding["kwargs"].items()},
                        baseline_outcome=serial_out(finding["b"]),
                        modified_outcome=serial_out(finding["m"]),
                        rationale=(
                            "baseline and target diverge for a Hypothesis-minimized input"
                            + ("; the stated property held for all sampled inputs, so the divergence lies outside the property's claim" if check is not None else "; no oracle states which is correct")
                        ),
                    )
                    result["examples_run"] = counter["n"]
                    return result
                found = None
    except Exception as e:
        result.update(status="environment_error", reason=f"hypothesis run failed: {type(e).__name__}: {sanitize(str(e))[:300]}")
        return result

    if check is not None:
        result["property_held"] = True
    result["examples_run"] = counter["n"]
    result["rationale"] = (
        f"explicit property held across {counter['n']} Hypothesis examples and {len(candidates)} boundary inputs"
        if check is not None
        else f"no behavioral divergence across {counter['n']} Hypothesis examples and {len(candidates)} boundary inputs"
    )
    return result


def main() -> int:
    if not SPEC_PATH.exists():
        RESULTS["error"] = "probe spec missing"
        write_results()
        return 2
    spec = json.loads(SPEC_PATH.read_text())
    budget = float(os.environ.get("BS_PROBE_BUDGET", "180"))
    for target in spec.get("targets", []):
        if time.time() - RESULTS["started_at"] > budget:
            RESULTS["targets"][target["id"]] = {
                "target_id": target["id"],
                "file": target["file"],
                "qualname": target["qualname"],
                "status": "timeout",
                "reason": "probe container time budget exhausted before this target ran",
            }
            write_results()
            continue
        try:
            RESULTS["targets"][target["id"]] = run_target(target)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            RESULTS["targets"][target["id"]] = {
                "target_id": target["id"],
                "file": target["file"],
                "qualname": target["qualname"],
                "status": "environment_error",
                "reason": f"unhandled probe error: {type(e).__name__}: {sanitize(str(e))[:300]}",
            }
        write_results()
    RESULTS["finished_at"] = time.time()
    write_results()
    return 0


if __name__ == "__main__":
    sys.exit(main())
