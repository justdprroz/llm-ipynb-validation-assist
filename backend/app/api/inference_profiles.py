from fastapi import APIRouter

from app.schemas import InferenceProfileCreate, InferenceProfileRead
from app.services import llm_proxy_client as lp

router = APIRouter(prefix="/settings/inference-profiles", tags=["settings"])


@router.get("", response_model=list[InferenceProfileRead])
def list_inference_profiles():
    return lp.list_profiles()


@router.post("", response_model=InferenceProfileRead, status_code=201)
def create_inference_profile(data: InferenceProfileCreate):
    return lp.create_profile(data)


@router.delete("/{profile_id}", status_code=204)
def delete_inference_profile(profile_id: str):
    lp.delete_profile(profile_id)
