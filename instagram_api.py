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

    def _log(msg: str):
        print(msg)
        if status_callback:
            status_callback(msg)

    def _err(resp) -> str:
        try:
            e = resp.json().get("error", {})
            return e.get("message") or e.get("error_user_msg") or str(e)
        except Exception:
            return resp.text[:300]

    with httpx.Client(timeout=600.0) as client:
        # Resolve user ID dynamically from /me (avoids stale INSTAGRAM_USER_ID secret)
        try:
            me = client.get(f"{GRAPH_API}/me", params={"fields": "id", "access_token": token})
            user_id = me.json()["id"]
            _log(f"Resolved user ID: {user_id}")
        except Exception as e:
            return {"success": False, "error": f"Could not resolve user ID: {e}"}

        # Step 1 — create media container
        _log("Creating media container...")
        try:
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
        except Exception as e:
            return {"success": False, "error": f"Network error: {e}"}

        _log(f"Container response: {data}")

        if "error" in data:
            return {"success": False, "error": f"Container error: {_err(resp)}"}

        container_id = data.get("id")
        if not container_id:
            return {"success": False, "error": f"No container ID — full response: {data}"}

        _log(f"Container {container_id} created. Waiting for processing...")

        # Step 2 — poll until processing complete (up to 10 min)
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
            return {"success": False, "error": f"Publish error: {_err(pr)}"}

        return {"success": True, "ig_id": pd.get("id")}
