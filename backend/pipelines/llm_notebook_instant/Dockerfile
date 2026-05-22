# Build from this directory with build context ``backend/pipelines`` so sibling
# ``llm_notebook_grader`` can be copied in CI:
#   docker build -f llm_notebook_instant/Dockerfile -t gradelab/pipeline-llm_notebook_instant:0.2.1 backend/pipelines
FROM python:3.12-slim
WORKDIR /build
COPY llm_notebook_instant/pyproject.toml llm_notebook_instant/gradelab_manifest.json ./llm_notebook_instant/
COPY llm_notebook_instant/llm_notebook_instant ./llm_notebook_instant/llm_notebook_instant
COPY llm_notebook_grader ./llm_notebook_grader
RUN pip install --no-cache-dir ./llm_notebook_grader \
    && pip install --no-cache-dir ./llm_notebook_instant
ENV PYTHONPATH=/usr/local/lib/python3.12/site-packages
WORKDIR /work
CMD ["python", "-c", "print('pipeline image ready; use gradelab_runner with mounted context')"]
