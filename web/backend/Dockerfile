FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY skilllab/ ./skilllab/
COPY web/backend/app.py ./web/backend/app.py
RUN pip install --no-cache-dir . fastapi "uvicorn[standard]"
ENV SKILLLAB_DIR=/lab
EXPOSE 8320
CMD ["uvicorn", "web.backend.app:app", "--host", "0.0.0.0", "--port", "8320"]
