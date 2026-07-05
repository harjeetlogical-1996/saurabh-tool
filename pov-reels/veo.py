"""
Veo 3 (Fast) video generation via the Gemini API.

One "generate" call returns a long-running operation; we poll it until the
video is ready, then download the mp4. Veo 3 Fast makes 8-second, 720p/1080p
vertical (9:16) clips WITH audio, from a text prompt.

Auth: the same Gemini API key you already use for nano-banana / reels-factory
(x-goog-api-key header). No extra account needed.

Docs shape (v1beta):
  POST models/{model}:predictLongRunning     -> {"name": "operations/..."}
  GET  operations/{name}                      -> {"done": true, "response": {...}}
The finished response carries the video either inline (base64) or as a short
lived download URI; we handle both.

Pricing (approx, changes over time — always confirm on Google's pricing page):
  veo-3.0-fast-generate-001  ~ $0.15 / second of output (audio included)
  veo-3.0-generate-001       ~ $0.40 / second (higher quality)
Every clip is 8s, so one Fast clip ~ $1.20, one HQ clip ~ $3.20.
"""
import os
import time
import base64
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).parent

# model id -> approx USD cost per second of generated video
VEO_MODELS = {
    "fast": ("veo-3.0-fast-generate-001", 0.15),
    "hq":   ("veo-3.0-generate-001",      0.40),
}
CLIP_SECONDS = 8               # Veo 3 always produces 8-second clips
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


def clip_cost(model: str = "fast") -> float:
    """USD cost of ONE 8-second Veo clip for the given model tier."""
    _, per_sec = VEO_MODELS.get(model, VEO_MODELS["fast"])
    return round(per_sec * CLIP_SECONDS, 2)


def estimate_cost(num_clips: int, model: str = "fast") -> dict:
    """
    Cost estimate for a whole reel BEFORE spending anything.
    Voice (Edge-TTS), captions and assembly are free/local, so the video
    clips are essentially the entire bill.
    """
    per = clip_cost(model)
    model_id, per_sec = VEO_MODELS.get(model, VEO_MODELS["fast"])
    return {
        "model": model_id,
        "clips": num_clips,
        "seconds_each": CLIP_SECONDS,
        "usd_per_second": per_sec,
        "usd_per_clip": per,
        "total_usd": round(per * num_clips, 2),
        "note": "Voice, captions, assembly and YouTube upload are free. "
                "Video generation is the whole cost.",
    }


def _req(url: str, key: str, payload: dict | None = None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Veo API {e.code}: {body}") from None


def generate_clip(prompt: str, out_path: Path, key: str,
                  model: str = "fast", aspect: str = "9:16",
                  negative: str = "", poll_every: int = 10,
                  timeout_s: int = 600) -> Path:
    """
    Generate ONE Veo clip from a text prompt and save it to out_path (.mp4).

    prompt:   what the scene shows AND says. For POV reels describe the
              character acting + the exact line it speaks, e.g.
              "A cute tomato with big eyes rolls across a wooden kitchen
               board, looking nervous, and says: 'Please don't put me in
               the salad, I have a family!'"
    model:    "fast" (cheap) or "hq" (best).
    aspect:   "9:16" vertical for Shorts/Reels, or "16:9".
    negative: things to avoid (e.g. "blurry, text, watermark").
    Returns the saved mp4 path. Raises on failure/timeout.
    """
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing (.env)")
    out_path = Path(out_path)
    model_id, _ = VEO_MODELS.get(model, VEO_MODELS["fast"])

    instances = {"prompt": prompt}
    params = {"aspectRatio": aspect}
    if negative:
        params["negativePrompt"] = negative

    start = _req(
        f"{API_ROOT}/models/{model_id}:predictLongRunning", key,
        payload={"instances": [instances], "parameters": params},
        method="POST")
    op_name = start.get("name")
    if not op_name:
        raise RuntimeError(f"No operation returned: {json.dumps(start)[:200]}")

    # poll until done
    deadline = time.time() + timeout_s
    op = start
    while not op.get("done"):
        if time.time() > deadline:
            raise RuntimeError(f"Veo timed out after {timeout_s}s (still rendering)")
        time.sleep(poll_every)
        op = _req(f"{API_ROOT}/{op_name}", key)

    if op.get("error"):
        raise RuntimeError(f"Veo failed: {json.dumps(op['error'])[:300]}")

    # dig the video out of the response (inline base64 OR a download uri)
    resp = op.get("response", {})
    vids = (resp.get("generatedVideos")
            or resp.get("generateVideoResponse", {}).get("generatedSamples")
            or resp.get("videos") or [])
    if not vids:
        # some shapes nest under 'predictions'
        vids = resp.get("predictions", [])
    if not vids:
        raise RuntimeError(f"No video in response: {json.dumps(resp)[:300]}")

    v = vids[0]
    video = v.get("video", v)
    b64 = video.get("bytesBase64Encoded") or video.get("videoBytes")
    uri = video.get("uri") or video.get("downloadUri") or v.get("uri")

    if b64:
        out_path.write_bytes(base64.b64decode(b64))
    elif uri:
        # download uri may itself need the api key appended
        dl = uri if "key=" in uri else f"{uri}{'&' if '?' in uri else '?'}key={key}"
        req = urllib.request.Request(dl, headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=180) as r:
            out_path.write_bytes(r.read())
    else:
        raise RuntimeError(f"No video bytes/uri in: {json.dumps(video)[:200]}")

    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise RuntimeError("Veo produced an empty file")
    return out_path
