from __future__ import annotations

import io
import json
import os
import re
import tarfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import docker
from docker.errors import ImageNotFound, NotFound

import logging

from app.config import settings

logger = logging.getLogger("branchsleuth.worker")

DOCKER_CONTEXT_DIR = Path(__file__).resolve().parents[3] / "docker"
MAX_LOG_BYTES = 64 * 1024
MAX_OUT_BYTES = 16 * 1024 * 1024
MAX_OUT_FILES = 5000

SECRET_PATTERNS = [
    re.compile(r"(postgres(?:ql)?(?:\+psycopg)?://[^\s\"']+)"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(sk-[A-Za-z0-9_\-]{20,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]{16,})"),
    re.compile(r"(npg_[A-Za-z0-9]+)"),
]


class WorkerUnavailable(RuntimeError):
    pass


class WorkerExecutionError(RuntimeError):
    def __init__(self, message: str, exit_code: int | None = None, timed_out: bool = False):
        super().__init__(message)
        self.exit_code = exit_code
        self.timed_out = timed_out


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


@dataclass
class TestPhaseResult:
    exit_code: int | None = None
    timed_out: bool = False
    tests: list = field(default_factory=list)
    collected: int = 0
    coverage_file: Path | None = None
    env_meta: dict = field(default_factory=dict)
    log: str = ""
    outcome: str = "unknown"


def get_docker_client() -> docker.DockerClient:
    try:
        client = docker.from_env(timeout=60)
        client.ping()
        return client
    except Exception as e:
        raise WorkerUnavailable(f"Docker daemon not reachable: {type(e).__name__}") from e


def ensure_worker_image(client: docker.DockerClient) -> str:
    image = settings.worker_image
    try:
        client.images.get(image)
        return image
    except ImageNotFound:
        pass
    if not (DOCKER_CONTEXT_DIR / "worker.Dockerfile").exists():
        raise WorkerUnavailable("worker image definition missing")
    try:
        client.images.build(
            path=str(DOCKER_CONTEXT_DIR),
            dockerfile="worker.Dockerfile",
            tag=image,
            rm=True,
        )
    except Exception as e:
        raise WorkerUnavailable(f"failed to build worker image: {redact(str(e))[:500]}") from e
    return image


def _resource_kwargs() -> dict:
    return {
        "mem_limit": settings.container_mem_bytes,
        "nano_cpus": int(settings.container_cpus * 1_000_000_000),
        "pids_limit": 256,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
    }


def _tar_dir(host_dir: Path, arc_prefix: str) -> bytes:
    buf = io.BytesIO()
    total = 0
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for root, dirs, files in os.walk(host_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", "node_modules")]
            for name in sorted(dirs):
                full = Path(root) / name
                rel = full.relative_to(host_dir).as_posix()
                ti = tarfile.TarInfo(name=f"{arc_prefix}/{rel}")
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                tf.addfile(ti)
            for name in sorted(files):
                full = Path(root) / name
                rel = full.relative_to(host_dir).as_posix()
                size = full.stat().st_size
                total += size
                if total > settings.max_extracted_bytes:
                    raise WorkerExecutionError("source tree exceeds size limit for container staging")
                ti = tarfile.TarInfo(name=f"{arc_prefix}/{rel}")
                ti.size = size
                ti.mode = 0o644
                with open(full, "rb") as fh:
                    tf.addfile(ti, fh)
    return buf.getvalue()


def _tar_bytes(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        ti = tarfile.TarInfo(name=name)
        ti.size = len(data)
        ti.mode = 0o644
        tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _extract_out_files(container, remote: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = remote.strip("/").split("/")[-1]
    try:
        stream, _stat = container.get_archive(remote)
    except NotFound:
        return []
    data = io.BytesIO()
    for chunk in stream:
        data.write(chunk)
    data.seek(0)
    written: list[Path] = []
    total = 0
    with tarfile.open(fileobj=data, mode="r") as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk() or member.name.startswith("/"):
                continue
            name = member.name.lstrip("./")
            if name == prefix:
                continue
            if name.startswith(f"{prefix}/"):
                name = name[len(f"{prefix}/"):]
            if not name or name.startswith(".."):
                continue
            target = (out_dir / name).resolve()
            if out_dir.resolve() not in target.parents and target != out_dir.resolve():
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            total += member.size
            if total > MAX_OUT_BYTES or len(written) > MAX_OUT_FILES:
                break
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as fh:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            written.append(target)
    return written


def prepare_environment(
    client: docker.DockerClient,
    run_key: str,
    baseline_dir: Path,
    modified_dir: Path,
    scripts_dir: Path,
) -> str:
    tag = f"bs-env-{run_key}"
    container = None
    try:
        baseline_tar = _tar_dir(baseline_dir, "baseline")
        modified_tar = _tar_dir(modified_dir, "modified")
        scripts_tar = _tar_dir(scripts_dir, "scripts")
        container = client.containers.create(
            image=settings.worker_image,
            command=["python", "/bs/scripts/prepare_env.py"],
            name=f"bs-prepare-{run_key}-{uuid.uuid4().hex[:8]}",
            environment={"BS_DEPS_TIMEOUT": str(settings.deps_timeout_seconds - 30)},
            **_resource_kwargs(),
        )
        container.put_archive("/bs", baseline_tar)
        container.put_archive("/bs", modified_tar)
        container.put_archive("/bs", scripts_tar)
        container.put_archive("/bs", _tar_bytes("out/.keep", b""))
        container.start()
        try:
            result = container.wait(timeout=settings.deps_timeout_seconds)
            exit_code = result.get("StatusCode")
        except Exception:
            container.kill()
            raise WorkerExecutionError("dependency preparation timed out", timed_out=True)
        if exit_code == 3:
            logs = container.logs().decode("utf-8", "replace")[-8000:]
            raise WorkerExecutionError(
                f"dependency installation failed:\n{redact(logs)}", exit_code=3
            )
        if exit_code != 0:
            logs = container.logs().decode("utf-8", "replace")[-4000:]
            raise WorkerExecutionError(f"environment preparation failed (exit {exit_code}):\n{redact(logs)}", exit_code=exit_code)
        container.commit(tag)
        return tag
    except WorkerExecutionError:
        raise
    except Exception as e:
        raise WorkerExecutionError(f"environment preparation error: {redact(str(e))[:500]}") from e
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


def run_tests(
    client: docker.DockerClient,
    env_image: str,
    run_key: str,
    src_root: str,
    phase: str,
) -> TestPhaseResult:
    out_dir = Path(settings.data_path()) / "tmp" / f"out-{run_key}-{phase}"
    result = TestPhaseResult()
    container = None
    container_name = f"bs-tests-{run_key}-{phase}-{uuid.uuid4().hex[:8]}"
    try:
        container = client.containers.create(
            image=env_image,
            command=["python", "/bs/scripts/run_tests.py", "--src", src_root],
            name=container_name,
            user="65534:65534",
            network_disabled=True,
            network_mode="none",
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "PYTHONPATH": f"{src_root}:/opt/deps:/bs/scripts",
                "COVERAGE_FILE": "/bs/out/.coverage",
                "HOME": "/tmp",
                "PYTHONPYCACHEPREFIX": "/tmp/pyc",
                "PYTHONDONTWRITEBYTECODE": "1",
                "HYPOTHESIS_DATABASE": "/tmp/hypothesis",
                "COLUMNS": "200",
            },
            **_resource_kwargs(),
        )
        container.start()
        try:
            wait = container.wait(timeout=settings.tests_timeout_seconds)
            result.exit_code = wait.get("StatusCode")
        except Exception:
            container.kill()
            result.timed_out = True
            result.exit_code = None
        logs = container.logs().decode("utf-8", "replace")
        result.log = redact(logs[-MAX_LOG_BYTES:])
        _extract_out_files(container, "/bs/out", out_dir)
        tests_json = out_dir / "test_results.json"
        if tests_json.exists():
            try:
                payload = json.loads(tests_json.read_text())
                result.tests = payload.get("tests", [])
                result.collected = payload.get("collected", 0)
            except json.JSONDecodeError:
                result.tests = []
        env_meta = out_dir / "env_meta.json"
        if env_meta.exists():
            try:
                result.env_meta = json.loads(env_meta.read_text())
            except json.JSONDecodeError:
                result.env_meta = {}
        cov = out_dir / ".coverage"
        if cov.exists() and cov.stat().st_size > 0:
            result.coverage_file = cov
        if result.exit_code == 0:
            result.outcome = "ok"
        elif result.timed_out:
            result.outcome = "timeout"
        elif result.exit_code == 5:
            result.outcome = "no_tests"
        else:
            result.outcome = "tests_failed"
        return result
    except Exception as e:
        result.outcome = "error"
        result.log = redact(f"{type(e).__name__}: {e}")[:MAX_LOG_BYTES]
        return result
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


def run_probes(
    client: docker.DockerClient,
    env_image: str,
    run_key: str,
    spec: dict,
) -> dict:
    out_dir = Path(settings.data_path()) / "tmp" / f"out-{run_key}-probe"
    container = None
    container_name = f"bs-probe-{run_key}-{uuid.uuid4().hex[:8]}"
    try:
        container = client.containers.create(
            image=env_image,
            command=["python", "/bs/scripts/run_probe.py"],
            name=container_name,
            user="65534:65534",
            network_disabled=True,
            network_mode="none",
            tmpfs={"/tmp": "rw,size=256m"},
            environment={
                "PYTHONPATH": "/opt/deps:/bs/scripts:/bs/baseline:/bs/modified",
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "BS_PROBE_BUDGET": str(max(60, settings.probe_timeout_seconds - 30)),
            },
            **_resource_kwargs(),
        )
        container.put_archive("/bs", _tar_bytes("spec/probe_spec.json", json.dumps(spec).encode()))
        container.start()
        timed_out = False
        try:
            container.wait(timeout=settings.probe_timeout_seconds)
        except Exception:
            container.kill()
            timed_out = True
        logs = redact(container.logs().decode("utf-8", "replace")[-MAX_LOG_BYTES:])
        _extract_out_files(container, "/bs/out", out_dir)
        probe_json = out_dir / "probe_results.json"
        payload: dict = {"targets": {}, "timed_out": timed_out, "log": logs}
        if probe_json.exists():
            try:
                parsed = json.loads(probe_json.read_text())
                parsed["timed_out"] = timed_out
                parsed["log"] = logs
                payload = parsed
            except json.JSONDecodeError:
                payload["parse_error"] = True
        return payload
    except Exception as e:
        return {"targets": {}, "timed_out": False, "log": redact(f"{type(e).__name__}: {e}")[:MAX_LOG_BYTES], "error": True}
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass


def cleanup_environment(client: docker.DockerClient, env_image: str) -> None:
    try:
        client.images.remove(env_image, force=True)
    except Exception:
        pass


class WorkerSession:
    def __init__(self, run_key: str):
        self.run_key = run_key
        self.client: docker.DockerClient | None = None
        self.env_image: str | None = None

    def __enter__(self) -> "WorkerSession":
        self.client = get_docker_client()
        ensure_worker_image(self.client)
        return self

    def prepare(self, baseline_dir: Path, modified_dir: Path) -> str:
        assert self.client is not None
        scripts = Path(__file__).parent / "scripts"
        self.env_image = prepare_environment(self.client, self.run_key, baseline_dir, modified_dir, scripts)
        return self.env_image

    def run_tests(self, src_root: str, phase: str) -> TestPhaseResult:
        assert self.client is not None and self.env_image is not None
        return run_tests(self.client, self.env_image, self.run_key, src_root, phase)

    def run_probes(self, spec: dict) -> dict:
        assert self.client is not None and self.env_image is not None
        return run_probes(self.client, self.env_image, self.run_key, spec)

    def close(self) -> None:
        if self.client is not None and self.env_image is not None:
            cleanup_environment(self.client, self.env_image)
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

    def __exit__(self, *exc) -> None:
        self.close()
