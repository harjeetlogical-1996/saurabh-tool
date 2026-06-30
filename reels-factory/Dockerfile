FROM python:3.12-slim

# System deps: FFmpeg for video, fonts for captions (Arial-like),
# fontconfig so libass/matplotlib find them.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fontconfig \
    fonts-dejavu \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Render/most clouds inject PORT; default 8000 locally.
ENV PORT=8000
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

# The server reads PORT + PUBLIC_URL from env (see server.py __main__).
CMD ["python", "server.py", "cloud"]
