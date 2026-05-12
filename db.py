import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client


def _cfg(key: str) -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        raise ValueError(f"Missing config: {key}")


def _db() -> Client:
    return create_client(_cfg("SUPABASE_URL"), _cfg("SUPABASE_KEY"))


def get_all_reels() -> list:
    return _db().table("reels").select("*").order("created_at", desc=True).execute().data or []


def add_reel(filename: str, caption: str, cloudinary_url: str, cloudinary_public_id: str) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "filename": filename,
        "caption": caption,
        "cloudinary_url": cloudinary_url,
        "cloudinary_public_id": cloudinary_public_id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = _db().table("reels").insert(row).execute()
    return result.data[0] if result.data else row


def update_status(reel_id: str, status: str) -> None:
    updates = {"status": status}
    if status == "posted":
        updates["posted_at"] = datetime.now(timezone.utc).isoformat()
    _db().table("reels").update(updates).eq("id", reel_id).execute()


def delete_reel(reel_id: str) -> None:
    _db().table("reels").delete().eq("id", reel_id).execute()


def get_oldest_approved() -> Optional[dict]:
    result = (
        _db().table("reels")
        .select("*")
        .eq("status", "approved")
        .order("created_at")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def was_posted_today() -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    result = (
        _db().table("reels")
        .select("id")
        .eq("status", "posted")
        .gte("posted_at", f"{today}T00:00:00+00:00")
        .execute()
    )
    return bool(result.data)
