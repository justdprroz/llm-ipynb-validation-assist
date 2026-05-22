"""Anytask integration using the anytask-scraper library directly."""

from __future__ import annotations

import dataclasses
import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import anytask_scraper
from anytask_scraper import (
    AnytaskClient,
    LoginError,
    ReviewQueue,
    download_submission_files,
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    format_student_folder,
    parse_course_page,
    parse_gradebook_page,
    parse_submission_page,
)
from anytask_scraper._queue_helpers import parse_ajax_entry
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.storage_client import storage_get_bytes, storage_put_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/anytask", tags=["integrations"])

COURSES_BUCKET = "courses"


class RealmImportBody(BaseModel):
    realm_name: str | None = None


def _get_client() -> AnytaskClient:
    settings = get_settings()
    if not settings.ANYTASK_USERNAME or not settings.ANYTASK_PASSWORD:
        raise HTTPException(status_code=503, detail="Set ANYTASK_USERNAME and ANYTASK_PASSWORD")
    # Enable the library's own debug logging so download/parse activity is visible
    anytask_scraper.setup_logging(level=logging.DEBUG)
    logger.debug("Logging in to anytask.org as %s", settings.ANYTASK_USERNAME)
    client = AnytaskClient(settings.ANYTASK_USERNAME, settings.ANYTASK_PASSWORD)
    try:
        client.login()
    except LoginError as exc:
        raise HTTPException(status_code=502, detail=f"Anytask login failed: {exc}") from exc
    logger.info("Logged in as %s", settings.ANYTASK_USERNAME)
    return client


def _safe_name(name: str, fallback: str) -> str:
    s = format_student_folder(name.strip()) if name.strip() else ""
    return s if s and s != "unknown" else fallback


def _store_json(course_id: str, name: str, data: dict) -> str:
    key = f"{course_id}/{name}.json"
    storage_put_bytes(
        COURSES_BUCKET, key,
        json.dumps(data, ensure_ascii=False, indent=2, default=str).encode(),
        content_type="application/json",
    )
    return key


def _upload_realm_zip(zip_bytes: bytes, name: str) -> dict:
    settings = get_settings()
    if not settings.STORAGE_MANAGER_URL:
        raise HTTPException(status_code=503, detail="STORAGE_MANAGER_URL not configured")
    headers = {"Authorization": f"Bearer {settings.STORAGE_MANAGER_TOKEN}"} if settings.STORAGE_MANAGER_TOKEN else {}
    logger.info("Uploading realm '%s' (%d bytes) to Storage Manager", name, len(zip_bytes))
    with httpx.Client(timeout=300.0) as http:
        r = http.post(
            f"{settings.STORAGE_MANAGER_URL.rstrip('/')}/v1/realms/upload",
            files={"file": ("realm.zip", zip_bytes, "application/zip")},
            data={"name": name},
            headers=headers,
        )
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    logger.info("Realm upload done: id=%s", r.json().get("id"))
    return r.json()


def _fetch_deep_queue(client: AnytaskClient, course_id: int) -> ReviewQueue:
    queue_html = client.fetch_queue_page(course_id)
    csrf = extract_csrf_from_queue_page(queue_html)
    if not csrf:
        raise HTTPException(status_code=502, detail="Could not extract CSRF token from queue page")
    entries = [parse_ajax_entry(row) for row in client.fetch_all_queue_entries(course_id, csrf)]
    logger.info("Queue: %d entries", len(entries))

    queue = ReviewQueue(course_id=course_id, entries=entries)
    accessible = [e for e in entries if e.has_issue_access and e.issue_url]
    logger.info("Fetching %d submission pages...", len(accessible))
    for i, entry in enumerate(accessible, 1):
        logger.debug("Submission %d/%d: %s", i, len(accessible), entry.issue_url)
        try:
            sub_html = client.fetch_submission_page(entry.issue_url)
            iid = extract_issue_id_from_breadcrumb(sub_html)
            if iid:
                queue.submissions[entry.issue_url] = parse_submission_page(sub_html, iid, issue_url=entry.issue_url)
        except Exception as exc:
            logger.debug("Skipping submission %s: %s", entry.issue_url, exc)
    logger.info("Fetched %d submissions with details", len(queue.submissions))
    return queue


@router.post("/courses/{course_id}/sync")
def sync_course(course_id: str) -> dict:
    """Fetch course, queue, and gradebook from anytask.org; store JSON in Storage Manager."""
    logger.info("sync_course: course_id=%s", course_id)
    client = _get_client()
    cid = int(course_id)
    artifacts: list[str] = []

    try:
        course = parse_course_page(client.fetch_course_page(cid), cid)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Course not found on anytask.org") from exc
    artifacts.append(_store_json(course_id, "course", dataclasses.asdict(course)))
    logger.info("Stored course '%s' (%d tasks)", course.title, len(course.tasks))

    queue_html = client.fetch_queue_page(cid)
    csrf = extract_csrf_from_queue_page(queue_html)
    entries = [parse_ajax_entry(row) for row in client.fetch_all_queue_entries(cid, csrf)] if csrf else []
    artifacts.append(_store_json(course_id, "queue", {
        "course_id": cid,
        "entries": [dataclasses.asdict(e) for e in entries],
        "submissions": {},
    }))
    logger.info("Stored queue (%d entries)", len(entries))

    try:
        gradebook = parse_gradebook_page(client.fetch_gradebook_page(cid), cid)
        artifacts.append(_store_json(course_id, "gradebook", dataclasses.asdict(gradebook)))
        logger.info("Stored gradebook")
    except Exception as exc:
        logger.warning("Gradebook unavailable: %s", exc)

    return {"course_id": course_id, "synced_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": artifacts, "bucket": COURSES_BUCKET}


@router.get("/courses/{course_id}")
def get_synced_course(course_id: str) -> dict:
    """Read synced course artifacts from Storage Manager."""
    out: dict = {"course_id": course_id, "artifacts": {}}
    for name in ("course", "queue", "gradebook"):
        try:
            out["artifacts"][name] = json.loads(storage_get_bytes(COURSES_BUCKET, f"{course_id}/{name}.json"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                out["artifacts"][name] = None
            else:
                raise HTTPException(status_code=502, detail=str(e)) from e
        except Exception:
            out["artifacts"][name] = None
    return out


@router.post("/courses/{course_id}/import-realm")
def import_course_as_realm(
    course_id: str,
    body: RealmImportBody = Body(default_factory=RealmImportBody),
) -> dict:
    """Download student notebooks from anytask.org and create a Storage Manager realm."""
    logger.info("import_course_as_realm: course_id=%s realm_name=%s", course_id, body.realm_name)
    client = _get_client()
    cid = int(course_id)

    try:
        course = parse_course_page(client.fetch_course_page(cid), cid)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Course not found on anytask.org") from exc
    logger.info("Course: '%s' (%d tasks)", course.title, len(course.tasks))

    realm_name = (body.realm_name or "").strip() or course.title.strip() or f"course_{course_id}"
    realm_folder = _safe_name(realm_name, f"course_{course_id}")

    queue = _fetch_deep_queue(client, cid)
    if not queue.submissions:
        raise HTTPException(status_code=422, detail="No accessible submissions found")

    zip_buffer = io.BytesIO()
    collected = 0

    with TemporaryDirectory(prefix="anytask-import-") as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for sub_obj in queue.submissions.values():
                task_dir = _safe_name(sub_obj.task_title, f"task_{sub_obj.issue_id}")
                student_stem = _safe_name(sub_obj.student_name, f"student_{sub_obj.issue_id}")

                # Let the library handle all download logic (auth retry, colab, validation)
                sub_tmp = tmp_dir / str(sub_obj.issue_id)
                downloaded = download_submission_files(client, sub_obj, sub_tmp)

                nb_files = [p for p in downloaded.values() if p.suffix == ".ipynb" and p.exists()]
                if not nb_files:
                    logger.debug("No notebook for %s / %s", sub_obj.student_name, sub_obj.task_title)
                    continue

                dest_arc = f"{realm_folder}/{task_dir}/students/{student_stem}.ipynb"
                zf.write(nb_files[0], arcname=dest_arc)
                logger.info("Added %s → %s", nb_files[0].name, dest_arc)
                collected += 1

    if collected == 0:
        raise HTTPException(status_code=422, detail="No student notebooks found in submissions")

    zip_buffer.seek(0)
    realm = _upload_realm_zip(zip_buffer.getvalue(), realm_name)
    homeworks = realm.get("homeworks") or []
    student_count = sum(int(h.get("student_count") or 0) for h in homeworks) or collected
    logger.info("Done: realm_id=%s homeworks=%d students=%d", realm.get("id"), len(homeworks), student_count)

    return {
        "realm_id": realm.get("id", ""),
        "realm_name": realm.get("name", realm_name),
        "homework_count": len(homeworks),
        "student_count": student_count,
    }
