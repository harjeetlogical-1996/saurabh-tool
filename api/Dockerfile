# syntax=docker/dockerfile:1.7
#
# Tool API (FastAPI) for Cloud Run.
# Includes ffmpeg + ffprobe in the runtime image because the audio→video
# and caption tools shell out to them per render.

# Python 3.12 (not 3.13) because faster-whisper's `av` dependency
# (PyAV 12.x) doesn't publish manylinux wheels for 3.13 yet, and
# building from source pulls in the full libav* dev headers and adds
# ~15 min to the build. 3.12 has prebuilt wheels for every dep.
FROM python:3.12-slim-bookworm AS runtime
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

# Pre-bake BOTH faster-whisper models into the image so cold starts
# never block on a download.
#   - "base"   (~140MB): English / auto-detect / Latin-script audio. ~5x
#     faster than 'medium', what most users actually want.
#   - "medium" (~1.5GB): Hindi / Urdu / other Indic scripts where 'base'
#     and 'small' would confuse Devanagari with Urdu on longer clips.
# tools/whisper_local.py picks between them based on the user's
# Language picker selection. Image size +1.6GB total; cold start is
# instant for either path.
ENV WHISPER_CACHE_DIR=/opt/whisper-models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8', download_root='/opt/whisper-models'); WhisperModel('medium', device='cpu', compute_type='int8', download_root='/opt/whisper-models')"

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
