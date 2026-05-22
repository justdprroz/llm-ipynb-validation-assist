from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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


class RealmRead(BaseModel):
    id: str
    name: str
    created_at: datetime | None
    path: str
    homeworks: list[HomeworkRead] = []
