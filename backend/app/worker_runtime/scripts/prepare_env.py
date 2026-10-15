import os
import subprocess
import sys

BS = "/bs"
DEPS = "/opt/deps"
PY = sys.executable


def main() -> int:
    os.makedirs(DEPS, exist_ok=True)
    os.makedirs(f"{BS}/out", exist_ok=True)
    os.chmod(f"{BS}/out", 0o1777)
    for sub in ("baseline", "modified", "scripts", "spec"):
        os.makedirs(f"{BS}/{sub}", exist_ok=True)

    req_candidates = []
    for root in (f"{BS}/modified", f"{BS}/baseline"):
        for name in ("requirements.txt", "requirements-dev.txt"):
            p = os.path.join(root, name)
            if os.path.isfile(p):
                req_candidates.append(p)
    installed = []
    install_note = "no requirements file found; running with worker environment"
    for req in req_candidates[:1]:
        proc = subprocess.run(
            [
                PY,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--timeout",
                "60",
                "--target",
                DEPS,
                "-r",
                req,
            ],
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("BS_DEPS_TIMEOUT", "240")),
        )
        if proc.returncode != 0:
            tail = (proc.stdout + "\n" + proc.stderr)[-4000:]
            print(f"dependency_install_failed\n{tail}", file=sys.stderr)
            return 3
        installed.append(req)
        install_note = f"installed dependencies from {os.path.basename(req)}"
        break

    meta = {
        "python_version": sys.version.split()[0],
        "dependencies": install_note,
    }
    import json

    with open(f"{BS}/out/env_meta.json", "w") as fh:
        json.dump(meta, fh)
    print(f"prepare_complete: {install_note}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        print("dependency_install_failed: pip exceeded its time budget", file=sys.stderr)
        sys.exit(3)
