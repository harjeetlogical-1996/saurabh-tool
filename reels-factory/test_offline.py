"""
Offline pipeline test: voice + captions + a generated solid-color background.
Does NOT need Pexels or Facebook keys. Proves FFmpeg assembly works.
"""
import subprocess
from pathlib import Path
import helpers

script = ("Did you know? Honey never spoils. "
          "Archaeologists found three thousand year old honey in Egyptian tombs, "
          "and it was still perfectly edible.")

stamp = "test"
voice_path = helpers.TEMP / f"voice_{stamp}.mp3"
print("1) voice...")
helpers.make_voice(script, voice_path, "en-US-AriaNeural")
dur = helpers.get_audio_duration(voice_path)
print(f"   voice {dur:.1f}s")

# fake background: generate a moving gradient with ffmpeg (no Pexels needed)
bg_path = helpers.TEMP / f"bg_{stamp}.mp4"
print("2) background (synthetic)...")
subprocess.run([
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s=1080x1920:d={dur:.2f}",
    "-vf", "noise=alls=20:allf=t",
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    str(bg_path),
], check=True, capture_output=True, text=True)
print("   bg done")

print("3) captions...")
ass = helpers.TEMP / f"cap_{stamp}.ass"
helpers.build_captions(script, dur, ass)

print("4) assemble...")
out = helpers.OUTPUT / f"offline_test.mp4"
helpers.build_reel(bg_path, voice_path, ass, out)
print(f"DONE -> {out}  ({out.stat().st_size} bytes)")
