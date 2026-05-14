# syntax=docker/dockerfile:1.7
#
# Tool API (FastAPI) for Cloud Run.
# Includes ffmpeg + ffprobe in the runtime image because the audio→video
# and caption tools shell out to them per render.

FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app

# System deps:
#  - ffmpeg / ffprobe: shelled out to by tools/audio_to_video.py and
#    tools/captions.py for actual encoding work.
#  - fonts-dejavu: Pillow placeholder renderer falls back to it; libass
#    also picks system fonts in addition to our bundled Inter.
#  - curl: optional, useful for in-container debugging via the Cloud Run
#    shell. Tiny size hit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-dejavu-core \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Python deps. razorpay is pulled in here too even though app.py imports
# it lazily — keeps the cold-start path snappy by avoiding a runtime
# `pip install`.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir razorpay==1.4.2

COPY . .

# Cloud Run gives us PORT (default 8080). The job worker pool lives
# inside the FastAPI process (see jobs.start_worker_thread) so a single
# container instance is fine for now.
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Invite-only gate stays ON in production. Owner bypasses it on their
# own. To open access later, flip this to 0 in the Cloud Run env.
ENV INVITE_GATE=1
# We DO want to allow user-scoped requests via the SSO cookie, never
# the dev_user_id query bypass — keep ALLOW_DEV_AUTH unset in prod.

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
