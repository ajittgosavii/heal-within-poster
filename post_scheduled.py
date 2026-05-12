"""
Runs daily via GitHub Actions.
Posts the oldest approved reel to Instagram, then marks it as posted.
"""
import sys
from datetime import datetime, timezone

from db import get_oldest_approved, update_status, was_posted_today
from instagram_api import post_reel


def main() -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Daily Reel Poster — starting")

    if was_posted_today():
        print("A reel was already posted today — skipping to avoid duplicates.")
        return

    reel = get_oldest_approved()
    if not reel:
        print("No approved reels in queue. Upload and approve one via the Streamlit app.")
        return

    print(f"Posting: {reel['filename']}  (ID: {reel['id']})")
    print(f"Caption preview: {reel['caption'][:100]}...")

    result = post_reel(reel["cloudinary_url"], reel["caption"])

    if result["success"]:
        update_status(reel["id"], "posted")
        print(f"SUCCESS — Instagram post ID: {result['ig_id']}")
    else:
        print(f"FAILED — {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
