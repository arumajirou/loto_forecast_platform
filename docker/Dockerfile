FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[api,postgres,mlflow]'
ENV LOTO_OUTPUT_DIR=/data
VOLUME ["/data"]
EXPOSE 8080
CMD ["uvicorn", "loto.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
