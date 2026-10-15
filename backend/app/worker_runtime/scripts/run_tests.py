import os
import sys

SRC = "/bs/src"
OUT = "/bs/out"


def main() -> int:
    args = sys.argv[1:]
    src = SRC
    if "--src" in args:
        src = args[args.index("--src") + 1]
    os.chdir(src)
    sys.path.insert(0, src)
    sys.path.insert(0, "/opt/deps")
    sys.path.insert(0, "/bs/scripts")
    os.environ["COVERAGE_FILE"] = f"{OUT}/.coverage"
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    import pytest

    pytest_args = [
        src,
        "-p",
        "no:cacheprovider",
        "-p",
        "bs_test_plugin",
        f"--cov={src}",
        "--cov-context=test",
        "--cov-report=",
        "-q",
        "--tb=short",
        "-ra",
        "--continue-on-collection-errors",
    ]
    exit_code = pytest.main(pytest_args)
    import json

    result_path = f"{OUT}/test_results.json"
    payload = {"tests": [], "collected": 0, "exit_status": int(exit_code)}
    if os.path.exists(result_path):
        with open(result_path) as fh:
            payload = json.load(fh)
    payload["exit_code"] = int(exit_code)
    payload["pytest_version"] = pytest.__version__
    cov_file = os.environ["COVERAGE_FILE"]
    payload["coverage_file_present"] = os.path.exists(cov_file)
    with open(result_path, "w") as fh:
        json.dump(payload, fh)
    return 0


if __name__ == "__main__":
    main()
