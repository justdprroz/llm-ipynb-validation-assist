from fastapi import APIRouter

from app.schemas import GitCredentialCreate, GitCredentialRead
from app.services import credential_service

router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[GitCredentialRead])
def list_credentials():
    return credential_service.list_credentials()


@router.post("", response_model=GitCredentialRead, status_code=201)
def create_credential(data: GitCredentialCreate):
    return credential_service.create_credential(data)


@router.delete("/{credential_id}", status_code=204)
def delete_credential(credential_id: str):
    credential_service.delete_credential(credential_id)
