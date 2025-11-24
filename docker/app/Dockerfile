FROM python:3.12-slim

# ffmpeg нужен для конвертации MP3 -> OGG/Opus (voice note)
RUN apt-get update -o Acquire::CompressionTypes::Order::=gz \
 && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*


WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
