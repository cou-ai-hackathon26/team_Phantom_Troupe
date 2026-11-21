FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-ben \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV BM25_PATH=/data/index/bm25.pkl
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
