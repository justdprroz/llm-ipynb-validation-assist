from fastapi import APIRouter, File, Form, UploadFile

from app.schemas import HomeworkRead, RealmRead
from app.services import storage_manager_client as sm

router = APIRouter(prefix="/realms", tags=["realms"])


@router.post("/upload", response_model=RealmRead, status_code=201)
async def upload_realm(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    return await sm.upload_realm(file, name)


@router.get("", response_model=list[RealmRead])
def list_realms():
    return sm.list_realms()


@router.get("/{realm_id}", response_model=RealmRead)
def get_realm(realm_id: str):
    return sm.get_realm(realm_id)


@router.get("/{realm_id}/homeworks/{homework_id}", response_model=HomeworkRead)
def get_homework(realm_id: str, homework_id: str):
    return sm.get_homework_detail(realm_id, homework_id)


@router.get("/{realm_id}/homeworks/{homework_id}/files/{file_path:path}")
def get_homework_file(realm_id: str, homework_id: str, file_path: str):
    return sm.get_file_content(realm_id, homework_id, file_path)


@router.post("/{realm_id}/homeworks/{homework_id}/gold", status_code=201)
async def upload_gold_file(realm_id: str, homework_id: str, file: UploadFile = File(...)):
    return await sm.upload_gold_file(realm_id, homework_id, file)


@router.delete("/{realm_id}", status_code=204)
def delete_realm(realm_id: str):
    sm.delete_realm(realm_id)
