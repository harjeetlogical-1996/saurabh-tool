"""
Image generation providers — pluggable FLUX-schnell adapters that sit
between the audio-to-video pipeline and the underlying APIs.

Each provider exposes the same surface:
    generate(prompt, style_prompt, size_ratio, out_path, *, seed=None) -> bool

The pipeline tries them in a configurable cost-ascending order and falls
back to the next provider on failure. Default order:
    together (cheapest) → replicate → fireworks → gemini → pollinations

All providers read API keys from runtime_config (admin UI) or env. Keys
are loaded lazily so a misconfigured provider doesn't crash startup —
it just gets skipped in the fallback chain.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Callable, Optional

import requests


# ---- Dimensions ----------------------------------------------------------

def _dims_for_ratio(size_ratio: str) -> tuple[int, int]:
    """FLUX-friendly multiples-of-16 sizes."""
    return {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1":  (1024, 1024),
        "4:5":  (864, 1080),
    }.get(size_ratio, (720, 1280))


def _orientation_hint(size_ratio: str) -> str:
    return {
        "9:16": "Vertical 9:16 portrait composition.",
        "16:9": "Horizontal 16:9 widescreen composition.",
        "1:1":  "Square 1:1 composition.",
        "4:5":  "Vertical 4:5 portrait composition.",
    }.get(size_ratio, "")


def _full_prompt(prompt: str, style_prompt: str, size_ratio: str) -> str:
    return (
        f"{prompt}. Style: {style_prompt}. {_orientation_hint(size_ratio)} "
        f"High quality, no text, no watermark, no logos."
    )


def _save_bytes(out_path: Path, data: bytes) -> bool:
    if len(data) < 2048:
        return False
    with open(out_path, "wb") as f:
        f.write(data)
    return True


def _key(name: str) -> Optional[str]:
    """Resolve a provider API key from runtime config first, env second."""
    try:
        from runtime_config import get_config_value
        v = get_config_value(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name.upper())


# ---- Provider: Together AI (FLUX schnell, ~$0.0027/img) -----------------

def generate_together(
    prompt: str, style_prompt: str, size_ratio: str,
    out_path: Path, *, seed: Optional[int] = None, retries: int = 2,
) -> bool:
    key = _key("togetherApiKey")
    if not key:
        return False
    w, h = _dims_for_ratio(size_ratio)
    body = {
        "model": "black-forest-labs/FLUX.1-schnell-Free",
        "prompt": _full_prompt(prompt, style_prompt, size_ratio),
        "width": w,
        "height": h,
        "steps": 4,           # schnell is 1-4 steps
        "n": 1,
        "response_format": "b64_json",
    }
    if seed is not None:
        body["seed"] = int(seed) & 0x7FFFFFFF
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.together.xyz/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60,
            )
            if r.status_code == 200:
                data = (r.json().get("data") or [{}])[0]
                b64 = data.get("b64_json")
                if b64:
                    return _save_bytes(out_path, base64.b64decode(b64))
                url = data.get("url")
                if url:
                    img = requests.get(url, timeout=60)
                    if img.status_code == 200:
                        return _save_bytes(out_path, img.content)
                last_err = "no image in response"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2.0 * (attempt + 1))
    print(f"[image.together] gave up: {last_err}")
    return False


# ---- Provider: Replicate (FLUX schnell, ~$0.003/img) --------------------

def generate_replicate(
    prompt: str, style_prompt: str, size_ratio: str,
    out_path: Path, *, seed: Optional[int] = None, retries: int = 2,
) -> bool:
    key = _key("replicateApiKey")
    if not key:
        return False
    w, h = _dims_for_ratio(size_ratio)
    aspect = {
        "9:16": "9:16", "16:9": "16:9", "1:1": "1:1", "4:5": "4:5",
    }.get(size_ratio, "9:16")
    input_payload = {
        "prompt": _full_prompt(prompt, style_prompt, size_ratio),
        "aspect_ratio": aspect,
        "num_outputs": 1,
        "num_inference_steps": 4,
        "output_format": "png",
        "output_quality": 95,
        "go_fast": True,
    }
    if seed is not None:
        input_payload["seed"] = int(seed) & 0x7FFFFFFF

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # Use Prefer: wait so Replicate blocks server-side until the run
        # finishes (or 60s) instead of us polling. Much simpler.
        "Prefer": "wait",
    }

    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                headers=headers,
                json={"input": input_payload},
                timeout=90,
            )
            if r.status_code in (200, 201):
                body = r.json()
                # Block until done if Replicate didn't already.
                status = body.get("status")
                while status in ("starting", "processing"):
                    time.sleep(1.0)
                    pid = body.get("id")
                    if not pid:
                        break
                    poll = requests.get(
                        f"https://api.replicate.com/v1/predictions/{pid}",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=30,
                    )
                    if poll.status_code != 200:
                        last_err = f"poll HTTP {poll.status_code}"
                        break
                    body = poll.json()
                    status = body.get("status")
                if status == "succeeded":
                    out = body.get("output")
                    url = out[0] if isinstance(out, list) and out else out
                    if isinstance(url, str) and url.startswith("http"):
                        img = requests.get(url, timeout=60)
                        if img.status_code == 200:
                            return _save_bytes(out_path, img.content)
                    last_err = "no output url"
                else:
                    last_err = f"status={status} err={body.get('error')}"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2.0 * (attempt + 1))
    print(f"[image.replicate] gave up: {last_err}")
    return False


# ---- Provider: Fireworks AI (FLUX schnell, ~$0.0035/img) ----------------

def generate_fireworks(
    prompt: str, style_prompt: str, size_ratio: str,
    out_path: Path, *, seed: Optional[int] = None, retries: int = 2,
) -> bool:
    key = _key("fireworksApiKey")
    if not key:
        return False
    w, h = _dims_for_ratio(size_ratio)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "image/jpeg",
    }
    body = {
        "prompt": _full_prompt(prompt, style_prompt, size_ratio),
        "width": w,
        "height": h,
        "steps": 4,
        "n": 1,
    }
    if seed is not None:
        body["seed"] = int(seed) & 0x7FFFFFFF
    last_err: Optional[str] = None
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.fireworks.ai/inference/v1/workflows/accounts/fireworks/models/flux-1-schnell-fp8/text_to_image",
                headers=headers,
                json=body,
                timeout=60,
            )
            if r.status_code == 200:
                # Image returned as raw bytes (image/jpeg)
                return _save_bytes(out_path, r.content)
            last_err = f"HTTP {r.status_code}: {r.text[:120]}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2.0 * (attempt + 1))
    print(f"[image.fireworks] gave up: {last_err}")
    return False


# ---- Provider chain orchestration ---------------------------------------

ProviderFn = Callable[..., bool]

# Cost-ascending default order. The pipeline still has Gemini + Pollinations
# wired as the final two layers (handled in audio_to_video.py for now); this
# module just owns the new cheap providers.
PROVIDER_REGISTRY: dict[str, ProviderFn] = {
    "together":   generate_together,
    "replicate":  generate_replicate,
    "fireworks":  generate_fireworks,
}

DEFAULT_ORDER = ("together", "replicate", "fireworks")


def _configured_order() -> list[str]:
    """
    Read the admin-configured priority order (comma-sep), falling back to
    DEFAULT_ORDER. Lets the operator e.g. demote Together if it's flaky.
    """
    try:
        from runtime_config import get_config_value
        raw = get_config_value("imageProviderOrder")
    except Exception:
        raw = None
    if not raw:
        return list(DEFAULT_ORDER)
    out = [p.strip() for p in raw.split(",") if p.strip() in PROVIDER_REGISTRY]
    return out or list(DEFAULT_ORDER)


def try_chain(
    prompt: str,
    style_prompt: str,
    size_ratio: str,
    out_path: Path,
    *,
    seed: Optional[int] = None,
) -> tuple[bool, str]:
    """
    Run providers in cost order. Returns (ok, source_name). On success,
    source_name is the provider that produced the image (e.g. 'together').
    On exhaustion, returns (False, 'none').

    This is what audio_to_video calls first — only if every cheap provider
    fails does it fall back to Gemini, then Pollinations.
    """
    order = _configured_order()
    last_tried = "none"
    for name in order:
        fn = PROVIDER_REGISTRY.get(name)
        if not fn:
            continue
        last_tried = name
        try:
            if fn(prompt, style_prompt, size_ratio, out_path, seed=seed):
                return True, name
        except Exception as e:
            print(f"[image.{name}] unexpected error: {e}")
    return False, last_tried
