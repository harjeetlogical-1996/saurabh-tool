"""
POV script writer — turns a topic ("a tomato's life", "a matchstick") into a
short, funny first-person reel: a list of scenes, each with

  - visual : a Veo prompt describing the character acting (fully animated)
  - line   : the exact sentence the character SAYS in that scene (voiceover
             + on-screen caption)

Uses the Gemini text API (same key). Falls back to a hand-written template if
the API is unavailable so the pipeline never hard-fails.
"""
import json
import urllib.request
import urllib.error

TEXT_MODEL = "gemini-2.5-flash"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM = """You write viral first-person ("POV: I am a ___") short-video scripts.
The narrator IS the object/character and talks directly to the viewer with
funny, relatable, slightly dramatic energy. Keep it wholesome and clean.

Return STRICT JSON only, no markdown, in this exact shape:
{
  "title": "<catchy YouTube Shorts title, <60 chars>",
  "hook": "<3-6 word on-screen hook for the first second>",
  "hashtags": ["#...", "#..."],
  "scenes": [
    {
      "visual": "<vivid Veo video prompt: describe the character, its
                  expression, the action, the setting, camera move. It is a
                  cartoon/3D animated character. NO on-screen text.>",
      "line": "<ONE short spoken sentence the character says, first person,
                <=16 words, punchy>"
    }
  ]
}
Rules: 3 to 5 scenes. Each 'line' <=16 words. The character speaks in first
person throughout. No dashes in the spoken lines. Make scene 1 a strong hook
and the last scene a funny or heart-tug button."""


def _fallback(topic: str) -> dict:
    subj = topic.strip() or "a tomato"
    name = subj.replace("a ", "").replace("the ", "").strip() or "tomato"
    return {
        "title": f"POV: I am {subj} #Shorts",
        "hook": f"I am {name}",
        "hashtags": ["#pov", "#funny", "#animation", "#shorts", "#satisfying"],
        "scenes": [
            {"visual": f"A cute expressive 3D cartoon {name} with big eyes sits on a "
                       f"kitchen board, morning light, slow push-in camera.",
             "line": f"Hi, I am {name}, and today is a very big day for me."},
            {"visual": f"The {name} looks up nervously as a giant knife shadow falls "
                       f"over it, dramatic lighting, slight shake.",
             "line": "Wait. Why is everyone looking at me like that?"},
            {"visual": f"The {name} tries to roll away fast across the counter, "
                       f"comedic motion blur, panicked face.",
             "line": "Nope, not today. I have so much left to give!"},
            {"visual": f"The {name} strikes a proud hero pose in a sunbeam, "
                       f"triumphant, sparkles around it.",
             "line": "Remember me. I was a good one. Follow for more."},
        ],
    }


def write_script(topic: str, key: str, style: str = "funny",
                 max_scenes: int = 5) -> dict:
    """
    Generate a POV script for `topic`. Returns the parsed dict (see SYSTEM).
    style: extra flavour, e.g. "funny", "emotional", "dramatic".
    Never raises — falls back to a template on any error.
    """
    if not key:
        return _fallback(topic)
    prompt = (f"{SYSTEM}\n\nTopic: {topic}\nTone: {style}\n"
              f"Use at most {max_scenes} scenes.")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0,
                             "responseMimeType": "application/json"},
    }
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{API_ROOT}/models/{TEXT_MODEL}:generateContent",
            data=data,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode())
        text = out["candidates"][0]["content"]["parts"][0]["text"]
        script = json.loads(text)
        # sanity: must have scenes with visual + line
        scenes = [s for s in script.get("scenes", [])
                  if s.get("visual") and s.get("line")]
        if not scenes:
            return _fallback(topic)
        script["scenes"] = scenes[:max_scenes]
        script.setdefault("title", f"POV: {topic} #Shorts")
        script.setdefault("hook", topic[:24])
        script.setdefault("hashtags", ["#pov", "#shorts", "#funny", "#animation"])
        return script
    except Exception:
        return _fallback(topic)
