FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "uvicorn[standard]>=0.29" "fastapi>=0.111" "boto3>=1.35" \
    "pydantic>=2.7" "pydantic-settings>=2.2" "python-multipart>=0.0.9" \
    "pymongo>=4.8.0" \
    "opentelemetry-sdk>=1.26.0" "opentelemetry-exporter-otlp-proto-grpc>=1.26.0" \
    "opentelemetry-instrumentation-fastapi>=0.47b0"
COPY src/storage_manager /app/storage_manager
ENV PYTHONPATH=/app
EXPOSE 8081
CMD ["sh", "-c", "uvicorn storage_manager.main:app --host 0.0.0.0 --port 8081 --log-level ${LOG_LEVEL:-debug} --access-log"]
