"""Run pipeline inside a sibling container (Docker-outside-of-Docker)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.pipeline_runner import run_pipeline_subprocess


def _use_docker() -> bool:
    return os.environ.get("GRADELAB_EXECUTOR_USE_DOCKER", "").strip().lower() in ("1", "true", "yes", "on")


def pipeline_image_for_run() -> str | None:
    return os.environ.get("PIPELINE_RUNNER_IMAGE") or os.environ.get("DEFAULT_PIPELINE_RUNNER_IMAGE")


def should_use_docker() -> bool:
    return _use_docker() and bool(pipeline_image_for_run())


def run_pipeline_via_docker(
    *,
    image: str,
    venv_python: Path,
    context_path: Path,
    entry_module: str,
    entry_function: str,
    run_id: str,
    extra_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Execute ``venv_python -m gradelab_runner`` inside ``image`` with shared ``/app/data`` and ``/app/pipelines``."""
    settings = get_settings()
    data_host = settings.DATA_DIR.resolve()
    pipelines_host = Path("/app/pipelines").resolve()
    data_mount_src = settings.DOCKER_HOST_DATA_DIR or str(data_host)
    pipelines_mount_src = settings.DOCKER_HOST_PIPELINES_DIR or str(pipelines_host)
    # Do not ``resolve()`` the venv ``python`` path: it is usually a symlink to the
    # system interpreter and would escape ``/app/data``, breaking ``relative_to``.
    venv_host = venv_python if venv_python.is_absolute() else (Path.cwd() / venv_python)
    rel = venv_host.relative_to(data_host)
    inner_venv = str(Path("/app/data") / rel)
    inner_ctx = f"/app/data/runs/{run_id}/scratch/{context_path.name}"

    network = os.environ.get("DOCKER_NETWORK", "gradelab_gradelab_net")

    cmd: list[str] = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "-v",
        f"{data_mount_src}:/app/data:rw",
        "-v",
        f"{pipelines_mount_src}:/app/pipelines:ro",
        "-w",
        "/app",
    ]
    for k, v in extra_env.items():
        if v is not None and v != "":
            cmd.extend(["-e", f"{k}={v}"])
    # Backend image sets ENTRYPOINT to uvicorn; override so we run the pipeline venv Python only.
    cmd.extend(
        [
            "--entrypoint",
            inner_venv,
            image,
            "-m",
            "gradelab_runner",
            "--context",
            inner_ctx,
            "--entry-module",
            entry_module,
            "--entry-function",
            entry_function,
        ]
    )
    return run_pipeline_subprocess(cmd)
