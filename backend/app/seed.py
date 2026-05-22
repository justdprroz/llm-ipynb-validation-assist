import io
import json
import zipfile
from pathlib import Path

import httpx

from app.config import get_settings
from app.mongo_store import get_mongo_db
from app.schemas import PipelineInstallRequest
from app.services import pipeline_service


STUDENTS = {
    "ivanov_ivan": {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Homework 1\n", "Linear algebra exercises"]},
            {"cell_type": "code", "metadata": {}, "source": ["import numpy as np"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["A = np.array([[1, 2], [3, 4]])"], "outputs": [], "execution_count": 2},
            {"cell_type": "code", "metadata": {}, "source": ["np.linalg.det(A)"], "outputs": [{"output_type": "execute_result", "data": {"text/plain": ["-2.0"]}}], "execution_count": 3},
            {"cell_type": "code", "metadata": {}, "source": ["np.linalg.inv(A)"], "outputs": [], "execution_count": 4},
            {"cell_type": "code", "metadata": {}, "source": ["eigenvalues = np.linalg.eig(A)\n", "print(eigenvalues)"], "outputs": [], "execution_count": 5},
            {"cell_type": "markdown", "metadata": {}, "source": ["## Results\n", "All computations completed."]},
        ],
    },
    "petrov_petr": {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# HW1"]},
            {"cell_type": "code", "metadata": {}, "source": ["x = 1"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["y = 2"], "outputs": [], "execution_count": 2},
        ],
    },
    "sidorova_anna": {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Homework 1 — Anna Sidorova"]},
            {"cell_type": "code", "metadata": {}, "source": ["import numpy as np\n", "import matplotlib.pyplot as plt"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["A = np.random.randn(3, 3)"], "outputs": [], "execution_count": 2},
            {"cell_type": "code", "metadata": {}, "source": ["U, S, V = np.linalg.svd(A)"], "outputs": [], "execution_count": 3},
            {"cell_type": "code", "metadata": {}, "source": ["print(f'Singular values: {S}')"], "outputs": [], "execution_count": 4},
            {"cell_type": "markdown", "metadata": {}, "source": ["## Conclusion\n", "SVD decomposition works as expected."]},
        ],
    },
    "kim_alex": {
        "cells": [
            {"cell_type": "code", "metadata": {}, "source": ["# no markdown, just code"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["2 + 2"], "outputs": [], "execution_count": 2},
        ],
    },
    "chen_wei": {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Homework 1"]},
            {"cell_type": "code", "metadata": {}, "source": ["import numpy as np"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["A = np.eye(5)"], "outputs": [], "execution_count": 2},
            {"cell_type": "code", "metadata": {}, "source": ["B = np.ones((5, 5))"], "outputs": [], "execution_count": 3},
            {"cell_type": "code", "metadata": {}, "source": ["C = A + B"], "outputs": [], "execution_count": 4},
            {"cell_type": "code", "metadata": {}, "source": ["np.linalg.det(C)"], "outputs": [], "execution_count": 5},
            {"cell_type": "code", "metadata": {}, "source": ["np.trace(C)"], "outputs": [], "execution_count": 6},
            {"cell_type": "markdown", "metadata": {}, "source": ["Done."]},
        ],
    },
}

GOLD = {
    "solution": {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Reference Solution"]},
            {"cell_type": "code", "metadata": {}, "source": ["import numpy as np"], "outputs": [], "execution_count": 1},
            {"cell_type": "code", "metadata": {}, "source": ["A = np.array([[1, 2], [3, 4]])"], "outputs": [], "execution_count": 2},
            {"cell_type": "code", "metadata": {}, "source": ["det = np.linalg.det(A)"], "outputs": [], "execution_count": 3},
            {"cell_type": "code", "metadata": {}, "source": ["inv = np.linalg.inv(A)"], "outputs": [], "execution_count": 4},
            {"cell_type": "code", "metadata": {}, "source": ["eig = np.linalg.eig(A)"], "outputs": [], "execution_count": 5},
            {"cell_type": "markdown", "metadata": {}, "source": ["All correct."]},
        ],
    },
}


def _make_notebook(cells: list[dict]) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": cells,
    }


def _build_seed_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in STUDENTS.items():
            nb = json.dumps(_make_notebook(data["cells"]))
            zf.writestr(f"linear_algebra_course/hw1/students/{name}.ipynb", nb)
        for name, data in GOLD.items():
            nb = json.dumps(_make_notebook(data["cells"]))
            zf.writestr(f"linear_algebra_course/hw1/gold/{name}.ipynb", nb)
    return buf.getvalue()


def seed() -> None:
    if get_mongo_db().realms.count_documents({}) > 0:
        return

    print("Seeding mock data...")
    settings = get_settings()
    base = (settings.STORAGE_MANAGER_URL or "").rstrip("/")
    if not base:
        print("  Skipping realm seed: STORAGE_MANAGER_URL not set")
        return

    headers: dict[str, str] = {}
    if settings.STORAGE_MANAGER_TOKEN:
        headers["Authorization"] = f"Bearer {settings.STORAGE_MANAGER_TOKEN}"

    zip_bytes = _build_seed_zip()
    files = {"file": ("seed-realm.zip", zip_bytes, "application/zip")}
    data = {"name": "Linear Algebra Course"}
    r = httpx.post(
        f"{base}/v1/realms/upload",
        files=files,
        data=data,
        headers=headers,
        timeout=120.0,
    )
    r.raise_for_status()
    print(f"  Realm seeded via Storage Manager: {r.json().get('id')}")

    request = PipelineInstallRequest(source_type="local", source_path="mock_pipeline")
    pipeline = pipeline_service.install_pipeline(request)
    print(f"  Pipeline '{pipeline.name}' installed (status={pipeline.status})")
    print("  Create a run from the UI (executor worker grades via ARQ).")
    print("Seed complete.")
