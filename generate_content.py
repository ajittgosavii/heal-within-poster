"""
Auto-generates Instagram Reels:
1. Downloads a healing/wellness stock video from Pexels
2. Downloads calming music from Pixabay
3. Merges video + audio using FFmpeg (30% music volume, 25s trim)
4. Generates caption + hashtags using OpenAI
5. Uploads to Cloudinary
6. Adds to Supabase queue as 'pending' (approve in Streamlit app)
"""
import os
import random
import uuid
import tempfile
import subprocess

import httpx
from openai import OpenAI
import cloudinary
import cloudinary.uploader

from db import add_reel

THEMES = [
    ("nature healing water", "about the healing power of water and nature"),
    ("meditation chakra yoga", "about chakra alignment, meditation, and inner balance"),
    ("candle spiritual zen", "about spiritual light, intention setting, and inner peace"),
    ("healing hands energy therapy", "about energy healing and releasing blockages"),
    ("abstract light cosmos energy", "about cosmic energy and universal healing"),
    ("mountain sunrise peaceful", "about new beginnings, strength, and peaceful mornings"),
    ("forest morning calm", "about grounding, connecting with nature, and clarity"),
    ("ocean waves tranquil", "about releasing what no longer serves you"),
]

MUSIC_TAGS_CCMIXTER = ["ambient+instrumental", "meditation+instrumental", "healing+ambient", "new+age+instrumental", "zen+instrumental"]
MUSIC_QUERIES_ARCHIVE = [
    "meditation instrumental ambient",
    "healing frequencies instrumental",
    "binaural meditation ambient",
    "nature sounds meditation instrumental",
    "chakra healing instrumental",
]


def _cfg(key: str) -> str:
    val = os.environ.get(key)
    if val:
        return val
    raise ValueError(f"Missing config: {key}")


def get_pexels_video(theme: str) -> str:
    api_key = _cfg("PEXELS_API_KEY")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            "https://api.pexels.com/videos/search",
            params={"query": theme, "orientation": "portrait", "size": "medium", "per_page": 15},
            headers={"Authorization": api_key},
        )
        data = resp.json()

    videos = data.get("videos", [])
    if not videos:
        raise ValueError(f"No Pexels videos found for: {theme}")

    video = random.choice(videos)
    files = sorted(video["video_files"], key=lambda x: x.get("width", 0), reverse=True)
    video_url = next((f["link"] for f in files if 400 <= f.get("width", 0) <= 1080), files[-1]["link"])

    tmp = os.path.join(tempfile.gettempdir(), f"hw_video_{uuid.uuid4().hex}.mp4")
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        with client.stream("GET", video_url) as r:
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    print(f"  Video downloaded: {os.path.getsize(tmp) // 1024} KB")
    return tmp


def get_background_music() -> str | None:
    """Try ccMixter first (CC-licensed, no key), then Archive.org as fallback."""
    return _get_ccmixter_music() or _get_archive_music()


def _get_ccmixter_music() -> str | None:
    # Use urllib instead of httpx — ccMixter sends oversized headers that trip httpx's buffer limit
    import urllib.request as _ur
    import json as _json
    tags = random.choice(MUSIC_TAGS_CCMIXTER)
    try:
        url = f"http://ccmixter.org/api/query?tags={tags}&f=json&limit=20"
        with _ur.urlopen(url, timeout=20) as resp:
            hits = _json.loads(resp.read())
        if not isinstance(hits, list):
            print(f"  ccMixter unexpected response type: {type(hits)}")
            return None

        # Filter out tracks with vocals by checking tags/name
        VOCAL_WORDS = {"vocal", "vocals", "voice", "singing", "singer", "lyric", "lyrics", "spoken", "rap", "hip hop"}
        valid = []
        for h in hits:
            track_tags = h.get("upload_tags", "").lower()
            track_name = h.get("upload_name", "").lower()
            if any(w in track_tags or w in track_name for w in VOCAL_WORDS):
                continue
            for f in h.get("files", []):
                dl = f.get("file_download_url", "")
                if dl and any(dl.lower().endswith(ext) for ext in (".mp3", ".ogg", ".wav")):
                    valid.append((dl, h.get("upload_name", "?")))
                    break

        if not valid:
            sample_keys = list(hits[0].keys()) if hits else []
            file_keys = list(hits[0]["files"][0].keys()) if hits and hits[0].get("files") else []
            print(f"  ccMixter: no downloadable files. hit keys={sample_keys} file keys={file_keys}")
            return None

        music_url, title = random.choice(valid[:20])
        print(f"  ccMixter track: {title}")
        tmp = os.path.join(tempfile.gettempdir(), f"hw_music_{uuid.uuid4().hex}.mp3")
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            r = client.get(music_url)
            with open(tmp, "wb") as f:
                f.write(r.content)
        print(f"  Music downloaded: {os.path.getsize(tmp) // 1024} KB")
        return tmp
    except Exception as e:
        print(f"  ccMixter error: {e}")
        return None


def _get_archive_music() -> str | None:
    """Fallback: free meditation music from Archive.org (no API key needed)."""
    import urllib.request as _ur
    import urllib.parse as _up
    import json as _json
    keyword = random.choice(MUSIC_QUERIES_ARCHIVE)
    try:
        params = _up.urlencode([
            ("q", f"{keyword} AND mediatype:audio"),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("output", "json"),
            ("rows", "25"),
            ("sort[]", "downloads desc"),
        ])
        search_url = f"https://archive.org/advancedsearch.php?{params}"
        with _ur.urlopen(search_url, timeout=30) as resp:
            docs = _json.loads(resp.read()).get("response", {}).get("docs", [])

        print(f"  Archive.org: {len(docs)} results for '{keyword}'")
        if not docs:
            return None

        random.shuffle(docs)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            for item in docs[:8]:
                identifier = item["identifier"]
                try:
                    meta = client.get(f"https://archive.org/metadata/{identifier}", timeout=15)
                    files = meta.json().get("files", [])
                except Exception:
                    continue
                SKIP_WORDS = {"vocal", "voice", "singing", "spoken", "rap", "lyric", "song"}
                mp3s = [
                    f for f in files
                    if f.get("name", "").lower().endswith(".mp3")
                    and 200_000 < int(f.get("size", 0) or 0) < 15_000_000
                    and not any(w in f.get("name", "").lower() for w in SKIP_WORDS)
                ]
                if not mp3s:
                    continue
                track = random.choice(mp3s[:3])
                music_url = f"https://archive.org/download/{identifier}/{track['name']}"
                print(f"  Archive.org track: {track['name']}")
                tmp = os.path.join(tempfile.gettempdir(), f"hw_music_{uuid.uuid4().hex}.mp3")
                r = client.get(music_url)
                with open(tmp, "wb") as f:
                    f.write(r.content)
                print(f"  Music downloaded: {os.path.getsize(tmp) // 1024} KB")
                return tmp

        print("  Archive.org: no usable MP3s in results")
        return None
    except Exception as e:
        print(f"  Archive.org error: {e}")
        return None


def process_video(video_path: str, music_path: str | None, duration: int = 25) -> str:
    output = os.path.join(tempfile.gettempdir(), f"hw_final_{uuid.uuid4().hex}.mp4")
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"

    if music_path:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-filter:a", "volume=0.35",
            "-shortest",
            output,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",
            output,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
    print(f"  Video processed: {os.path.getsize(output) // 1024} KB")
    return output


def generate_caption(topic: str) -> str:
    client = OpenAI(api_key=_cfg("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"""Write an Instagram Reel caption for @healwithinbyaparna — a certified CHQM Healer
who helps women align their chakras, release blockages, and step into their true power.

This Reel is {topic}.

Requirements:
- Open with a powerful sentence (no emoji at the very start)
- 3-5 sentences of warm, spiritual, nurturing content
- End with a gentle call to action (follow, comment, book a session)
- Add a line break then 15-20 relevant hashtags
- Keep under 2000 characters total

Return only the caption, no extra commentary."""
        }],
        max_tokens=500,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()


def main():
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc).isoformat()}] Content generator — starting")

    cloudinary.config(
        cloud_name=_cfg("CLOUDINARY_CLOUD_NAME"),
        api_key=_cfg("CLOUDINARY_API_KEY"),
        api_secret=_cfg("CLOUDINARY_API_SECRET"),
    )

    theme_keyword, theme_topic = random.choice(THEMES)
    print(f"Theme: {theme_keyword}")

    print("Downloading stock video from Pexels...")
    video_path = get_pexels_video(theme_keyword)

    print("Downloading background music...")
    music_path = get_background_music()

    print("Processing video with FFmpeg...")
    final_video = process_video(video_path, music_path)

    print("Generating caption with OpenAI...")
    caption = generate_caption(theme_topic)
    print(f"Caption: {caption[:120]}...")

    print("Uploading to Cloudinary...")
    public_id = f"healwithin/auto/{uuid.uuid4().hex}"
    result = cloudinary.uploader.upload(
        final_video,
        resource_type="video",
        public_id=public_id,
        overwrite=True,
    )
    cloudinary_url = result["secure_url"]
    print(f"Cloudinary URL: {cloudinary_url}")

    filename = f"auto_{theme_keyword.replace(' ', '_')}_{uuid.uuid4().hex[:8]}.mp4"
    reel = add_reel(
        filename=filename,
        caption=caption,
        cloudinary_url=cloudinary_url,
        cloudinary_public_id=public_id,
    )
    print(f"Added to queue — ID: {reel['id']} — approve in Streamlit app")

    for path in [video_path, final_video] + ([music_path] if music_path else []):
        if path and os.path.exists(path):
            os.remove(path)

    print("Done!")


if __name__ == "__main__":
    main()
