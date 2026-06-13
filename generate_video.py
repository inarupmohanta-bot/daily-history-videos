"""
Daily Animated Video Generator (100% free-tier tools)
"""

import os
import json
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

import requests
import edge_tts
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
VOICE = "en-IN-PrabhatNeural"
VIDEO_SIZE = (1080, 1920)
OUTPUT_DIR = Path("output")
WORK_DIR = Path("work")
OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

client = genai.Client(api_key=GEMINI_API_KEY)


def generate_script():
    prompt = """You create scripts for short, punchy 30-45 second vertical
animated "History Bites" videos aimed at maximizing YouTube Shorts and
Instagram Reels engagement today.

Pick ONE little-known but fascinating true historical event, figure, or
fact (any era, any region of the world - mix it up across requests:
ancient civilizations, world wars, Indian history, science history,
exploration, etc.). Prefer stories with a surprising twist or "wow,
I didn't know that" angle.

Return STRICT JSON only, no markdown, in this exact format:
{
  "title": "short catchy video title (max 60 chars)",
  "topic": "2-3 word visual search term for background images matching the era/setting",
  "script": "the full narration script, 60-100 words, written for voiceover - start with a hook, tell the story, end with a punchy closing line",
  "lines": ["short caption line 1", "short caption line 2", "..."]
}
The "lines" should be the script split into 5-8 short caption chunks
(max ~8 words each) in the order they're spoken.
"""
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


async def generate_voiceover(script_text, out_path):
    communicate = edge_tts.Communicate(script_text, VOICE)
    await communicate.save(str(out_path))


def get_audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def fetch_images(query, count=6):
    headers = {"Authorization": PEXELS_API_KEY}
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params={"query": query, "per_page": count, "orientation": "portrait"},
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    paths = []
    for i, photo in enumerate(photos):
        url = photo["src"]["portrait"]
        img_path = WORK_DIR / f"img_{i}.jpg"
        with open(img_path, "wb") as f:
            f.write(requests.get(url).content)
        paths.append(img_path)
    return paths


def build_image_clip(img_path, duration, out_path, zoom_in=True):
    w, h = VIDEO_SIZE
    fps = 30
    frames = int(duration * fps)
    if zoom_in:
        zoom_expr = "min(zoom+0.0008,1.3)"
    else:
        zoom_expr = "if(lte(zoom,1.0),1.3,max(1.0,zoom-0.0008))"

    vf = (
        f"scale=-2:{h*2},"
        f"zoompan=z='{zoom_expr}':d={frames}:s={w}x{h}:fps={fps},"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf", vf, "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_srt(lines, total_duration, srt_path):
    n = len(lines)
    per = total_duration / n
    srt = []
    for i, line in enumerate(lines):
        start = i * per
        end = (i + 1) * per
        srt.append(f"{i+1}")
        srt.append(f"{format_ts(start)} --> {format_ts(end)}")
        srt.append(line)
        srt.append("")
    srt_path.write_text("\n".join(srt), encoding="utf-8")


def format_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    print("Generating script via Gemini...")
    data = generate_script()
    print(json.dumps(data, indent=2))

    title = data["title"]
    script_text = data["script"]
    lines = data["lines"]
    topic = data["topic"]

    audio_path = WORK_DIR / "voice.mp3"
    asyncio.run(generate_voiceover(script_text, audio_path))
    duration = get_audio_duration(audio_path)
    print(f"Voiceover duration: {duration:.1f}s")

    print(f"Fetching images for: {topic}")
    images = fetch_images(topic, count=max(4, int(duration // 5) + 1))
    if not images:
        images = fetch_images("abstract background", count=4)

    per_clip_duration = duration / len(images)
    clip_paths = []
    for i, img in enumerate(images):
        out = WORK_DIR / f"clip_{i}.mp4"
        build_image_clip(img, per_clip_duration, out, zoom_in=(i % 2 == 0))
        clip_paths.append(out)

    concat_file = WORK_DIR / "concat.txt"
    with open(concat_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    silent_video = WORK_DIR / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c", "copy", str(silent_video)],
        check=True, capture_output=True
    )

    srt_path = WORK_DIR / "captions.srt"
    build_srt(lines, duration, srt_path)

    today = datetime.now().strftime("%Y%m%d")
    final_path = OUTPUT_DIR / f"video_{today}.mp4"

    subtitle_style = (
        "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,"
        "Alignment=2,MarginV=120"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(silent_video),
        "-i", str(audio_path),
        "-vf", f"subtitles={srt_path}:force_style='{subtitle_style}'",
        "-c:v", "libx264", "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        str(final_path)
    ]
    subprocess.run(cmd, check=True)

    meta = {
        "title": title,
        "description": script_text + "\n\n#shorts #history #historyfacts #didyouknow",
        "file": str(final_path),
    }
    (OUTPUT_DIR / f"meta_{today}.json").write_text(json.dumps(meta, indent=2))

    print(f"\nDone! Video saved to {final_path}")
    print(f"Title: {title}")


if __name__ == "__main__":
    main()
