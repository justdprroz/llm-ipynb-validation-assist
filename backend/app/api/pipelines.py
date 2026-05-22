import io

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas import PipelineInstallRequest, PipelineRead
from app.services import pipeline_service

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=list[PipelineRead])
def list_pipelines():
    return pipeline_service.list_pipelines()


@router.post("/install", response_model=PipelineRead, status_code=201)
def install_pipeline(request: PipelineInstallRequest):
    return pipeline_service.install_pipeline(request)


@router.get("/template")
def download_template():
    content = pipeline_service.generate_template_zip()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=gradelab_pipeline_template.zip"},
    )


@router.post("/upload", response_model=PipelineRead, status_code=201)
async def upload_pipeline(file: UploadFile = File(...)):
    return await pipeline_service.upload_and_install_pipeline(file)


@router.get("/{pipeline_id}", response_model=PipelineRead)
def get_pipeline(pipeline_id: str):
    return pipeline_service.get_pipeline(pipeline_id)


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str):
    pipeline_service.delete_pipeline(pipeline_id)
