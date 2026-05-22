"""Run service (Mongo-backed)."""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from app.services import run_mongo


def create_run(run_create: Any, background_tasks: BackgroundTasks) -> Any:
    return run_mongo.create_run(run_create, background_tasks)


def execute_run(run_id: str) -> None:
    return run_mongo.execute_run(run_id)


def list_runs(
    pipeline_id: str | None = None,
    homework_id: str | None = None,
    status: str | None = None,
) -> Any:
    return run_mongo.list_runs(pipeline_id=pipeline_id, homework_id=homework_id, status=status)


def get_run(run_id: str) -> Any:
    return run_mongo.get_run(run_id)


def get_run_results(run_id: str) -> Any:
    return run_mongo.get_run_results(run_id)


def get_viewer_adjustments(run_id: str) -> Any:
    return run_mongo.get_viewer_adjustments(run_id)


def put_viewer_adjustments(run_id: str, payload: Any) -> Any:
    return run_mongo.put_viewer_adjustments(run_id, payload)


def compare_runs(run_ids: list[str]) -> dict:
    return run_mongo.compare_runs(run_ids)
