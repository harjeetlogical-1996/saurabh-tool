"""
Local Whisper transcription via faster-whisper (CTranslate2 backend).

Returns the same {word, start, end} shape as the Gemini transcriber in
tools/captions.py so callers can swap providers without other changes.

Why this exists:
  - Gemini gives APPROXIMATED timestamps because we ask it via prompt.
    That's why captions drift out of sync with the audio on longer clips.
  - Whisper gives NATIVE word-level alignment, so captions land on the
    actual word boundaries.
  - No per-call cost; runs entirely on CPU. Bigger memory footprint
    than Gemini-over-HTTP, but constant — no rate limits, no quota.

Model selection (model_size_or_path):
  - "tiny":   ~75MB,   ~5x realtime. English-only OK; Hindi very poor.
  - "base":   ~140MB,  ~2x realtime. English OK; Hindi outputs Urdu
              script (vocabularies overlap and base lacks Devanagari).
  - "small":  ~460MB,  ~1x realtime. Hindi mostly Devanagari, decent.
  - "medium": ~1.5GB,  ~0.3x realtime. Best Hindi/Hinglish accuracy
              without a GPU.

We default to "medium" — Hindi captions are the primary use case for
this project and the smaller models confuse Hindi with Urdu.
Override via the WHISPER_MODEL env var.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional


_MODEL_LOCK = threading.Lock()
# faster-whisper's WhisperModel.transcribe is NOT safe to call concurrently
# from multiple threads — under the hood it shares CTranslate2 state that
# corrupts or deadlocks with parallel access. The job-worker pool runs 3
# threads, so without this serialising lock a second simultaneous caption
# job would hang at the transcribe step. We lock around the actual decode
# call only — model loading still uses its own lock above.
_TRANSCRIBE_LOCK = threading.Lock()
# Set while a transcribe is actively running, so other workers can show
# a "Waiting in queue" message instead of pretending to be transcribing.
TRANSCRIBE_BUSY = threading.Event()

# Cache of loaded WhisperModel instances keyed by model size. Cold-start
# pays the model-load cost once per size; subsequent transcribes reuse
# the loaded instance. Two models max — "base" for fast/English/Auto
# paths and "medium" for Hindi/Urdu (needs robust Devanagari support).
_MODELS: dict[str, "WhisperModel"] = {}  # type: ignore[name-defined]


# Language → model picker. Hindi / Urdu / other Indic scripts go to the
# heavier "medium" model — small still confused Devanagari with Urdu on
# longer clips. English, auto-detect, and everything else stays on
# "base" — 5-10x faster and accurate enough for Latin-script audio.
_HEAVY_LANGUAGES = {"hi", "ur", "bn", "ta", "te", "mr", "gu", "kn", "pa", "ml"}


def _pick_model_size(language: Optional[str]) -> str:
    """Smart routing: heavy-script langs get 'medium', everyone else
    gets 'base'. Env var override (WHISPER_MODEL) wins for testing."""
    forced = os.environ.get("WHISPER_MODEL")
    if forced:
        return forced
    if language and language.lower() in _HEAVY_LANGUAGES:
        return "medium"
    return "base"


def _get_model(language: Optional[str] = None):
    """Load and cache the right-sized model for this language. First
    call for each size pays the cold-start cost (download if missing
    + load into RAM); subsequent calls return the cached instance."""
    size = _pick_model_size(language)
    cached = _MODELS.get(size)
    if cached is not None:
        return cached
    with _MODEL_LOCK:
        cached = _MODELS.get(size)
        if cached is not None:
            return cached
        from faster_whisper import WhisperModel
        # int8 quantisation: same accuracy on CPU, half the RAM + faster.
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        print(f"[whisper_local] loading model={size} device={device} compute={compute_type}")
        _MODELS[size] = WhisperModel(
            size,
            device=device,
            compute_type=compute_type,
            # Cache in a stable folder so the model survives container
            # restarts without re-downloading.
            download_root=os.environ.get("WHISPER_CACHE_DIR", "/tmp/whisper_models")
                if os.name != "nt"
                else os.environ.get("WHISPER_CACHE_DIR"),
        )
        print(f"[whisper_local] model loaded: {size}")
        return _MODELS[size]


def transcribe_words_local(
    audio_path: Path,
    language: Optional[str] = None,
    on_progress: Optional[Any] = None,
) -> list[dict]:
    """
    Returns [{word, start, end}, ...] with word-level timestamps.
    Compatible with the Gemini transcriber's output shape.

    `on_progress(fraction: float, seg_end: float, duration: float)` is
    called after each segment is decoded so the caller can update a
    job-progress bar in real time. Whisper's segments generator yields
    progressively as decoding proceeds — yielding per-segment lets us
    surface "30% of audio transcribed" instead of a frozen 15%.

    Whisper occasionally emits the leading space attached to a word
    (" hello"). We strip that here so downstream punctuation cleanup
    in captions.py gets clean tokens.
    """
    # Language hint: passed-in param > env var > auto-detect. Hindi and
    # Urdu are phonetically close, so on short clips Whisper's auto can
    # flip. Setting language="hi" locks it. "auto"/None lets it choose.
    lang = language if (language and language != "auto") else (
        os.environ.get("WHISPER_LANGUAGE") or None
    )
    # Pick the right-sized model for this language. English/auto use the
    # fast 'base' model; Hindi/Urdu/other Indic scripts use 'small'.
    model = _get_model(lang)
    # The transcribe call + the segments-generator drain must BOTH be
    # inside the lock — the generator references model state that gets
    # rewritten by the next call. Releasing after .transcribe() but
    # before consuming the generator would race.
    words: list[dict] = []
    with _TRANSCRIBE_LOCK:
        TRANSCRIBE_BUSY.set()
        try:
            return _do_transcribe(model, audio_path, lang, on_progress)
        finally:
            TRANSCRIBE_BUSY.clear()


def _do_transcribe(model, audio_path: Path, lang, on_progress) -> list[dict]:
    """Inner transcribe — called only with _TRANSCRIBE_LOCK held."""
    words: list[dict] = []
    segments, info = model.transcribe(
        str(audio_path),
        language=lang,
        word_timestamps=True,
        vad_filter=True,
    )
    duration = float(getattr(info, "duration", 0.0)) or 0.0
    for seg in segments:
        if seg.words:
            for w in seg.words:
                txt = (w.word or "").strip()
                if not txt:
                    continue
                try:
                    s = float(w.start)
                    e = float(w.end)
                except (TypeError, ValueError):
                    continue
                if e < s:
                    e = s + 0.1
                words.append({"word": txt, "start": s, "end": e})
        # Stream progress after each segment regardless of whether
        # it contained words — keeps the bar moving on quiet stretches.
        if on_progress and duration > 0:
            try:
                seg_end = float(seg.end)
                on_progress(min(1.0, seg_end / duration), seg_end, duration)
            except Exception:
                pass
    return words
