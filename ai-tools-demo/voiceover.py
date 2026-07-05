"""Text-to-speech: Gemini TTS first, free Edge-TTS as fallback.

Gemini's TTS returns raw PCM (signed 16-bit, 24kHz, mono). We wrap it in a WAV
header ourselves so we don't need scipy/pydub. Edge-TTS produces mp3 directly.

If GEMINI_API_KEY is missing or the call fails for any reason (quota, network,
bad key), we silently fall back to Edge-TTS so the pipeline never blocks.
"""
import asyncio
import os
import struct
import wave

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _gemini_tts(text: str, out_path: str) -> bool:
    """Try Gemini TTS. Returns True on success, False to trigger fallback."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        voice = os.environ.get("GEMINI_VOICE", "Kore").strip() or "Kore"

        # Try models in order. Newest first; older flash model has a tiny free
        # daily cap so it's last. GEMINI_MODEL env overrides the whole list.
        env_model = os.environ.get("GEMINI_MODEL", "").strip()
        models = [env_model] if env_model else [
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-pro-preview-tts",
            "gemini-2.5-flash-preview-tts",
        ]

        import time

        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            ),
        )

        pcm = None
        for model in models:
            # Retry a couple of times on transient rate limits (429) before
            # giving up on this model and trying the next.
            for attempt in range(3):
                try:
                    resp = client.models.generate_content(
                        model=model, contents=text, config=cfg
                    )
                    pcm = resp.candidates[0].content.parts[0].inline_data.data
                    break
                except Exception as e:
                    if os.environ.get("TTS_DEBUG"):
                        print(f"   [gemini {model} attempt {attempt}] {str(e)[:160]}")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        time.sleep(20)  # per-minute limit -> wait and retry
                        continue
                    break  # non-rate-limit error: stop retrying this model
            if pcm:
                break  # got audio, stop trying models

        if not pcm:
            return False

        # Wrap raw PCM (24kHz, 16-bit, mono) into a proper WAV file.
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm)
        return os.path.getsize(out_path) > 1000
    except Exception:
        return False


def _edge_tts(text: str, out_path: str) -> bool:
    """Free Microsoft Edge TTS fallback. Writes mp3 to out_path."""
    try:
        import edge_tts

        voice = os.environ.get("EDGE_VOICE", "en-IN-NeerjaNeural").strip()

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(out_path)

        asyncio.run(_run())
        return os.path.exists(out_path) and os.path.getsize(out_path) > 500
    except Exception:
        return False


def make_voiceover(text: str, name: str = "voiceover") -> dict:
    """Generate a voiceover file from text. Returns {"path", "engine"}.

    Tries Gemini (-> .wav), falls back to Edge-TTS (-> .mp3).
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_")) or "voiceover"

    wav_path = os.path.join(OUTPUT_DIR, f"{safe}.wav")
    if _gemini_tts(text, wav_path):
        return {"path": wav_path, "engine": "gemini"}

    mp3_path = os.path.join(OUTPUT_DIR, f"{safe}.mp3")
    if _edge_tts(text, mp3_path):
        return {"path": mp3_path, "engine": "edge-tts"}

    raise RuntimeError(
        "Both Gemini and Edge-TTS failed. Check internet / GEMINI_API_KEY."
    )
