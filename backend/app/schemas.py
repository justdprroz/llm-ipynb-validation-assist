from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskResult(BaseModel):
    task_id: str
    score: float
    max_score: float
    status: str
    comment: str | None = None


class StudentResult(BaseModel):
    student_id: str
    tasks: list[TaskResult]
    total_score: float
    report: str | None = None
    metadata: dict[str, Any] | None = None


class InferenceCredentials(BaseModel):
    """Resolved inference profile passed to pipeline run(context)."""

    provider: str
    model: str
    api_key: str
    yc_folder: str | None = None
    profile_id: str | None = None
    profile_name: str | None = None
    is_dummy: bool = False


class RunContext(BaseModel):
    run_id: str
    homework_dir: str
    students_dir: str
    gold_dir: str
    student_files: list[str]
    scratch_dir: str
    config: dict[str, Any] = {}
    credentials: InferenceCredentials | None = None


class PipelineOutput(BaseModel):
    results: list[StudentResult]
    metadata: dict[str, Any] | None = None


class FileEntry(BaseModel):
    name: str
    path: str


class HomeworkRead(BaseModel):
    id: str
    realm_id: str
    name: str
    student_count: int | None
    gold_count: int | None
    student_files: list[FileEntry] = []
    gold_files: list[FileEntry] = []

    model_config = {"from_attributes": True}


class RealmCreate(BaseModel):
    name: str


class RealmRead(BaseModel):
    id: str
    name: str
    created_at: datetime | None
    path: str
    homeworks: list[HomeworkRead] = []

    model_config = {"from_attributes": True}


class PipelineInstallRequest(BaseModel):
    source_type: Literal["local", "whl", "git"]
    source_path: str


class PipelineRead(BaseModel):
    id: str
    name: str
    version: str
    source: str
    source_path: str
    entry_module: str
    entry_function: str
    description: str | None
    installed_at: datetime | None
    status: str
    runner_image: str | None = None

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    pipeline_id: str | None = None
    pipeline_name: str | None = None
    pipeline_version: str | None = None
    homework_id: str
    inference_profile_id: str | None = None
    pipeline_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_pipeline_ref(self) -> RunCreate:
        if self.pipeline_id:
            return self
        if self.pipeline_name and self.pipeline_version:
            return self
        raise ValueError("Provide pipeline_id or both pipeline_name and pipeline_version")


class RunRead(BaseModel):
    id: str
    pipeline_id: str | None = None
    homework_id: str
    pipeline_name: str | None = None
    homework_name: str | None = None
    inference_profile_id: str | None = None
    inference_profile_name: str | None = None
    inference_provider: str | None = None
    inference_model: str | None = None
    inference_is_dummy: bool | None = None
    status: str
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    run_metadata: dict[str, Any] | None = None
    pipeline_config: dict[str, Any] | None = None

    model_config = {"from_attributes": True}

    @field_validator("run_metadata", mode="before")
    @classmethod
    def parse_run_metadata(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("pipeline_config", mode="before")
    @classmethod
    def parse_pipeline_config(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v


class RunResultRead(BaseModel):
    id: str
    run_id: str
    student_id: str
    total_score: float
    tasks: list[TaskResult] = []
    report: str | None
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_tasks_json(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            raw = getattr(data, "tasks_json", None)
            metadata_raw = getattr(data, "result_metadata", None)
            obj = {
                "id": data.id,
                "run_id": data.run_id,
                "student_id": data.student_id,
                "total_score": data.total_score,
                "report": data.report,
                "tasks": json.loads(raw) if isinstance(raw, str) else (raw or []),
                "metadata": json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw,
            }
            return obj
        if isinstance(data, dict) and "tasks_json" in data:
            raw = data.pop("tasks_json")
            data["tasks"] = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return data


class ViewerAdjustmentPayload(BaseModel):
    """Persisted viewer overlay: exclude students from aggregates/report; optional per-task scores (0–1)."""

    v: int = 1
    excluded_student_ids: list[str] = Field(default_factory=list)
    task_scores: dict[str, dict[str, float]] = Field(default_factory=dict)

    @field_validator("excluded_student_ids", mode="before")
    @classmethod
    def strip_excluded(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return v
        seen: set[str] = set()
        out: list[str] = []
        for x in v:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    @field_validator("task_scores", mode="before")
    @classmethod
    def normalize_task_scores(cls, v: Any) -> Any:
        if v is None:
            return {}
        if not isinstance(v, dict):
            return v
        out: dict[str, dict[str, float]] = {}
        for sid, inner in v.items():
            if not isinstance(sid, str) or not sid.strip():
                continue
            if not isinstance(inner, dict):
                continue
            row: dict[str, float] = {}
            for tid, score in inner.items():
                if not isinstance(tid, str) or not tid.strip():
                    continue
                if isinstance(score, (int, float)):
                    row[tid.strip()] = float(score)
            if row:
                out[sid.strip()] = row
        return out

    @model_validator(mode="after")
    def validate_scores(self) -> ViewerAdjustmentPayload:
        for sid, inner in self.task_scores.items():
            for tid, score in inner.items():
                if score < 0 or score > 1:
                    raise ValueError(f"task_scores[{sid!r}][{tid!r}] must be in [0, 1], got {score}")
        return self


class ViewerAdjustmentResponse(BaseModel):
    payload: ViewerAdjustmentPayload
    updated_at: datetime | None = None


class GitCredentialCreate(BaseModel):
    host: str
    token: str
    description: str | None = None


class GitCredentialRead(BaseModel):
    id: str
    host: str
    token_preview: str
    description: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class InferenceProfileCreate(BaseModel):
    name: str
    provider: str
    model: str
    api_key: str
    yc_folder: str | None = None
    description: str | None = None
    is_dummy: bool = False
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    openrouter_provider: dict[str, Any] | None = None
    effort: str | None = None


class InferenceProfileRead(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    api_key_preview: str
    yc_folder: str | None
    description: str | None
    is_dummy: bool
    created_at: datetime | None
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    openrouter_provider: dict[str, Any] | None = None
    effort: str | None = None

    model_config = {"from_attributes": True}


class CompareEntry(BaseModel):
    student_id: str
    run_a_score: float | None
    run_b_score: float | None
    run_a_tasks: list[TaskResult] = []
    run_b_tasks: list[TaskResult] = []


class CompareResponse(BaseModel):
    run_a: RunRead
    run_b: RunRead
    entries: list[CompareEntry]


class NotebookCell(BaseModel):
    cell_type: str
    source: str
    outputs: list[dict[str, Any]] = []


class NotebookContent(BaseModel):
    cells: list[NotebookCell]
    metadata: dict[str, Any] = {}


class FileContent(BaseModel):
    path: str
    filename: str
    content_type: Literal["notebook", "text"]
    notebook: NotebookContent | None = None
    text: str | None = None
