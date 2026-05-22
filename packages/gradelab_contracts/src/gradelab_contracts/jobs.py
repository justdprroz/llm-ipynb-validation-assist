from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StorageRef(BaseModel):
    bucket: str
    prefix: str


class InferenceProfileRef(BaseModel):
    profile_id: str


class RunJobV1(BaseModel):
    """Redis / ARQ job body: gradelab.run_job.v1."""

    model_config = ConfigDict(populate_by_name=True)

    job_schema: Literal["gradelab.run_job.v1"] = Field(
        default="gradelab.run_job.v1",
        alias="schema",
    )
    run_id: str
    attempt: int = Field(ge=1, default=1)
    pipeline_name: str
    pipeline_version: str
    entry_module: str
    entry_function: str
    homework_storage_ref: StorageRef
    scratch_storage_ref: StorageRef
    inference_profile_ref: InferenceProfileRef | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    trace_context: dict[str, str] = Field(default_factory=dict)
