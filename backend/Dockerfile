FROM python:3.11-slim
WORKDIR /app
# Unbuffered output so `docker logs` shows progress while models load.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# cv2 (pulled in by easyocr/ultralytics) links against libGL/libglib even in a
# server image; without these libraries the container dies on `import cv2`.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# data/uploads holds per-request images (deleted after each request);
# data/models holds the trained fusion model. Both live under the mounted
# /app/data volume so they survive container replacement.
RUN mkdir -p data/uploads data/models
EXPOSE 8000
# A single worker is deliberate: OCR, CLIP and YOLO are cached per process, and
# extra workers would multiply that memory instead of sharing it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
