import io
import json
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from app.config import get_settings
from app.mongo_repo import pipeline_delete, pipeline_get, pipeline_insert, pipeline_list
from app.schemas import PipelineInstallRequest
from app.services import credential_service


def _pipeline_from_doc(doc: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=doc["_id"],
        name=doc["name"],
        version=doc["version"],
        source=doc["source"],
        source_path=doc["source_path"],
        entry_module=doc["entry_module"],
        entry_function=doc["entry_function"],
        description=doc.get("description"),
        installed_at=doc.get("installed_at"),
        status=doc["status"],
        runner_image=doc.get("runner_image"),
    )


def _runner_image_env() -> str | None:
    return os.environ.get("PIPELINE_RUNNER_IMAGE") or os.environ.get("DEFAULT_PIPELINE_RUNNER_IMAGE")


def _persist_pipeline_doc(doc: dict[str, object]) -> SimpleNamespace:
    if "runner_image" not in doc or doc["runner_image"] is None:
        doc = {**doc, "runner_image": _runner_image_env()}
    pipeline_insert(doc)
    return _pipeline_from_doc(doc)


def _read_manifest(source_path: Path) -> dict:
    manifest_file = source_path / "gradelab_manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"gradelab_manifest.json not found in {source_path}")
    with open(manifest_file) as f:
        data = json.load(f)
    required = {"name", "version", "entry_module", "entry_function"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Manifest missing required fields: {missing}")
    return data


def _create_venv(venv_path: Path) -> None:
    result = subprocess.run(
        ["python", "-m", "venv", str(venv_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"venv creation failed: {result.stderr}")


def _pip_install(venv_path: Path, package_path: str) -> None:
    venv_root = venv_path.resolve()
    py = venv_root / "bin" / "python"
    if not py.exists():
        raise RuntimeError(f"venv python not found: {py}")
    pp = Path(package_path).resolve()
    cwd = str(pp) if pp.is_dir() else None
    result = subprocess.run(
        [str(py), "-m", "pip", "install", str(pp)],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pip install failed for {package_path}: {result.stderr}")


def _maybe_install_llm_notebook_grader_sibling(
    venv_path: Path, source_path: Path, pipeline_name: str
) -> None:
    if not pipeline_name.startswith("llm_notebook"):
        return
    sibling = source_path.parent / "llm_notebook_grader"
    if sibling.is_dir() and (sibling / "pyproject.toml").exists():
        _pip_install(venv_path, str(sibling))


def install_pipeline(request: PipelineInstallRequest) -> SimpleNamespace:
    settings = get_settings()
    clone_dir: Path | None = None

    if request.source_type == "local":
        source_path = Path("/app/pipelines") / request.source_path
    elif request.source_type == "git":
        parsed = urlparse(request.source_path)
        host = parsed.hostname or ""
        cred = credential_service.get_credential_for_host(host)

        clone_url = request.source_path
        if cred:
            port_part = f":{parsed.port}" if parsed.port else ""
            clone_url = f"{parsed.scheme}://oauth2:{cred.token}@{parsed.hostname}{port_part}{parsed.path}"

        clone_dir = Path(tempfile.mkdtemp())
        result = subprocess.run(
            ["git", "clone", clone_url, str(clone_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            shutil.rmtree(clone_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=f"Git clone failed: {result.stderr}")
        source_path = clone_dir
    else:
        source_path = Path(request.source_path)

    try:
        manifest = _read_manifest(source_path)
    except (FileNotFoundError, ValueError) as exc:
        if clone_dir is not None:
            shutil.rmtree(clone_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    name = manifest["name"]
    venv_path = settings.PIPELINE_VENVS_DIR / name
    pipeline_id = str(uuid.uuid4())
    status = "installed"

    try:
        _create_venv(venv_path)
        _maybe_install_llm_notebook_grader_sibling(venv_path, source_path, name)
        _pip_install(venv_path, str(source_path))
        _pip_install(venv_path, "/app/app/runner/")
    except RuntimeError:
        status = "broken"
    finally:
        if clone_dir is not None:
            shutil.rmtree(clone_dir, ignore_errors=True)

    doc = {
        "_id": pipeline_id,
        "name": name,
        "version": manifest["version"],
        "source": request.source_type,
        "source_path": str(source_path),
        "entry_module": manifest["entry_module"],
        "entry_function": manifest["entry_function"],
        "description": manifest.get("description"),
        "installed_at": datetime.utcnow(),
        "status": status,
    }
    return _persist_pipeline_doc(doc)


def _find_manifest_dir(root: Path) -> Path | None:
    if (root / "gradelab_manifest.json").exists():
        return root
    for child in root.iterdir():
        if child.is_dir() and (child / "gradelab_manifest.json").exists():
            return child
    return None


async def upload_and_install_pipeline(file: UploadFile) -> SimpleNamespace:
    filename = file.filename or "upload"
    if not (filename.endswith(".zip") or filename.endswith(".whl")):
        raise HTTPException(status_code=422, detail="Only .zip and .whl files are supported")

    settings = get_settings()

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        if filename.endswith(".zip"):
            extract_dir = Path(tempfile.mkdtemp())
            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(extract_dir)

                source_path = _find_manifest_dir(extract_dir)
                if source_path is None:
                    raise HTTPException(status_code=422, detail="gradelab_manifest.json not found in archive")

                manifest = _read_manifest(source_path)
                name = manifest["name"]
                venv_path = settings.PIPELINE_VENVS_DIR / name

                status = "installed"
                try:
                    _create_venv(venv_path)
                    _maybe_install_llm_notebook_grader_sibling(venv_path, source_path, name)
                    _pip_install(venv_path, str(source_path))
                    _pip_install(venv_path, "/app/app/runner/")
                except RuntimeError:
                    status = "broken"

                doc = {
                    "_id": str(uuid.uuid4()),
                    "name": name,
                    "version": manifest["version"],
                    "source": "upload",
                    "source_path": filename,
                    "entry_module": manifest["entry_module"],
                    "entry_function": manifest["entry_function"],
                    "description": manifest.get("description"),
                    "installed_at": datetime.utcnow(),
                    "status": status,
                }
                return _persist_pipeline_doc(doc)
            finally:
                shutil.rmtree(extract_dir, ignore_errors=True)

        whl_name = Path(filename).stem.split("-")[0]
        venv_path = settings.PIPELINE_VENVS_DIR / whl_name

        status = "installed"
        try:
            _create_venv(venv_path)
            _pip_install(venv_path, str(tmp_path))
            _pip_install(venv_path, "/app/app/runner/")
        except RuntimeError:
            status = "broken"

        site_packages = venv_path / "lib" / "python3.12" / "site-packages"
        manifest_files = list(site_packages.glob("**/gradelab_manifest.json"))
        if not manifest_files:
            shutil.rmtree(venv_path, ignore_errors=True)
            raise HTTPException(status_code=422, detail="gradelab_manifest.json not found in wheel package")

        manifest = _read_manifest(manifest_files[0].parent)
        name = manifest["name"]

        if whl_name != name:
            correct_path = settings.PIPELINE_VENVS_DIR / name
            if venv_path.exists():
                shutil.move(str(venv_path), str(correct_path))
            venv_path = correct_path

        doc = {
            "_id": str(uuid.uuid4()),
            "name": name,
            "version": manifest["version"],
            "source": "upload",
            "source_path": filename,
            "entry_module": manifest["entry_module"],
            "entry_function": manifest["entry_function"],
            "description": manifest.get("description"),
            "installed_at": datetime.utcnow(),
            "status": status,
        }
        return _persist_pipeline_doc(doc)

    finally:
        tmp_path.unlink(missing_ok=True)


def list_pipelines() -> list[SimpleNamespace]:
    return [_pipeline_from_doc(d) for d in pipeline_list()]


def get_pipeline(pipeline_id: str) -> SimpleNamespace:
    doc = pipeline_get(pipeline_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return _pipeline_from_doc(doc)


def delete_pipeline(pipeline_id: str) -> None:
    pipeline = get_pipeline(pipeline_id)
    settings = get_settings()
    venv_path = settings.PIPELINE_VENVS_DIR / pipeline.name
    pipeline_delete(pipeline_id)
    if venv_path.exists():
        shutil.rmtree(venv_path)


def generate_template_zip() -> bytes:
    pyproject_toml = """\
[project]
name = "my-pipeline"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"
"""

    manifest_json = json.dumps(
        {
            "name": "my_pipeline",
            "version": "0.1.0",
            "entry_module": "my_pipeline.main",
            "entry_function": "run",
            "description": "My custom pipeline",
        },
        indent=2,
    )

    main_py = '''\
from pathlib import Path
import json


def run(context: dict) -> dict:
    """
    GradeLab pipeline entry point.

    context keys:
        run_id (str): Unique run identifier
        homework_dir (str): Path to homework directory
        students_dir (str): Path to students/ subdirectory
        gold_dir (str): Path to gold/ subdirectory
        student_files (list[str]): Paths to student .ipynb files
        scratch_dir (str): Writable directory for intermediate results
        config (dict): Optional tuning (effort, reasoning, retry, debug).
        credentials (dict|None): If the run used an inference profile: provider, model,
            api_key, yc_folder, profile_id, profile_name, is_dummy.

    Must return a dict with structure:
        {
            "results": [
                {
                    "student_id": str,       # filename stem, e.g. "ivanov_ivan"
                    "tasks": [
                        {
                            "task_id": str,      # e.g. "task_1"
                            "score": float,      # 0.0 to 1.0 normalized
                            "max_score": float,  # display value, e.g. 10.0
                            "status": str,       # "pass"|"fail"|"partial"|"error"|"skipped"
                            "comment": str|None  # optional feedback
                        }
                    ],
                    "total_score": float,    # 0.0 to 1.0 normalized
                    "report": str|None,      # optional free-text report
                    "metadata": dict|None    # optional extras
                }
            ],
            "metadata": dict|None    # optional pipeline-level metadata
        }
    """
    results = []

    for student_file in context["student_files"]:
        student_id = Path(student_file).stem

        with open(student_file) as f:
            notebook = json.load(f)

        # Your grading logic here
        tasks = [
            {
                "task_id": "example_task",
                "score": 1.0,
                "max_score": 10.0,
                "status": "pass",
                "comment": None,
            }
        ]

        results.append({
            "student_id": student_id,
            "tasks": tasks,
            "total_score": sum(t["score"] for t in tasks) / len(tasks),
            "report": None,
            "metadata": None,
        })

    return {"results": results, "metadata": None}
'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("my_pipeline/pyproject.toml", pyproject_toml)
        zf.writestr("my_pipeline/gradelab_manifest.json", manifest_json)
        zf.writestr("my_pipeline/my_pipeline/__init__.py", "")
        zf.writestr("my_pipeline/my_pipeline/main.py", main_py)
    return buf.getvalue()
