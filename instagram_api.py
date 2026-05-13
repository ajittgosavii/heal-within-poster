import os
import time
from typing import Optional, Callable

import httpx

GRAPH_API = "https://graph.instagram.com/v21.0"


def _cfg(key: str) -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        raise ValueError(f"Missing config: {key}")


def check_connection() -> dict:
    try:
        token = _cfg("INSTAGRAM_ACCESS_TOKEN")
    except ValueError as e:
        return {"connected": False, "message": str(e)}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{GRAPH_API}/me",
                params={"fields": "id,username,name", "access_token": token},
            )
            data = resp.json()
    except Exception as e:
        return {"connected": False, "message": f"Network error: {e}"}

    if "error" in data:
        return {"connected": False, "message": data["error"].get("message", "Auth failed")}

    if data.get("username"):
        return {
            "connected": True,
            "username": data.get("username", "healwithinbyaparna"),
            "name": data.get("name", ""),
            "ig_id": data.get("id"),
        }

    return {"connected": False, "message": "Could not retrieve Instagram account info."}


def post_reel(
    cloudinary_url: str,
    caption: str,
    status_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    token = _cfg("INSTAGRAM_ACCESS_TOKEN")
    user_id = _cfg("INSTAGRAM_USER_ID")

    def _log(msg: str):
        print(msg)
        if status_callback:
            status_callback(msg)

    with httpx.Client(timeout=600.0) as client:
        # Step 1 — create media container
        _log("Creating media container...")
        resp = client.post(
            f"{GRAPH_API}/{user_id}/media",
            params={
                "media_type": "REELS",
                "video_url": cloudinary_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": token,
            },
        )
        data = resp.json()

        if "error" in data:
            return {"success": False, "error": data["error"].get("message", "Container creation failed")}

        container_id = data.get("id")
        if not container_id:
            return {"success": False, "error": "No container ID returned — check API permissions"}

        _log(f"Container {container_id} created. Waiting for Instagram to process video...")

        # Step 2 — poll until processing is complete (up to 10 min)
        for attempt in range(60):
            time.sleep(10)
            sr = client.get(
                f"{GRAPH_API}/{container_id}",
                params={"fields": "status_code", "access_token": token},
            )
            status = sr.json().get("status_code", "UNKNOWN")
            _log(f"Processing ({attempt + 1}/60): {status}")

            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                return {"success": False, "error": f"Video processing failed: {status}"}
        else:
            return {"success": False, "error": "Video processing timed out after 10 minutes"}

        # Step 3 — publish
        _log("Publishing reel to Instagram...")
        pr = client.post(
            f"{GRAPH_API}/{user_id}/media_publish",
            params={"creation_id": container_id, "access_token": token},
        )
        pd = pr.json()

        if "error" in pd:
            return {"success": False, "error": pd["error"].get("message", "Publish failed")}

        return {"success": True, "ig_id": pd.get("id")}
