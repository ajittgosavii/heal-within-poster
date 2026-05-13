import streamlit as st
import cloudinary
import cloudinary.uploader
from datetime import datetime, timezone

from db import get_all_reels, add_reel, update_status, delete_reel
from instagram_api import check_connection, post_reel

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Heal Within — Reel Scheduler",
    page_icon="🪷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Brand CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] > .main {
    background: linear-gradient(160deg, #1a0a2e 0%, #2d1155 60%, #1a0a2e 100%);
    background-attachment: fixed;
}
[data-testid="stHeader"] { background: rgba(26,10,46,0.95); border-bottom: 1px solid rgba(212,175,55,0.3); }
.heal-header {
    background: linear-gradient(135deg, #2d1155 0%, #6B2D8B 100%);
    border: 1px solid rgba(212,175,55,0.4);
    border-radius: 14px;
    padding: 22px 28px;
    margin-bottom: 16px;
}
.heal-title { font-size: 1.9rem; font-weight: 700; color: #D4AF37; letter-spacing: 2px; margin: 0; }
.heal-sub   { color: #b09ec0; font-size: 0.88rem; margin-top: 4px; }
.section-title {
    color: #D4AF37;
    font-size: 1.05rem;
    font-weight: 600;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(212,175,55,0.2);
    margin-bottom: 14px;
}
.stTabs [data-baseweb="tab-list"] {
    background: rgba(45,17,85,0.7);
    border-radius: 10px;
    gap: 4px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"]          { border-radius: 8px; color: #b09ec0; padding: 8px 22px; }
.stTabs [aria-selected="true"]        { background: rgba(107,45,139,0.55) !important; color: #D4AF37 !important; }
.status-pending  { background: rgba(255,152,0,0.15); color: #FF9800; border: 1px solid rgba(255,152,0,0.35);
                   padding: 3px 12px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
.status-approved { background: rgba(76,175,80,0.15); color: #4CAF50; border: 1px solid rgba(76,175,80,0.35);
                   padding: 3px 12px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
.status-posted   { background: rgba(212,175,55,0.15); color: #D4AF37; border: 1px solid rgba(212,175,55,0.35);
                   padding: 3px 12px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
.info-box {
    background: rgba(45,17,85,0.55);
    border: 1px solid rgba(212,175,55,0.2);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #D4AF37, #f0d060);
    color: #1a0a2e;
    font-weight: 700;
    border: none;
}
</style>
""", unsafe_allow_html=True)


# ── Cloudinary init (once per session) ────────────────────────────────────────
@st.cache_resource
def _init_cloudinary():
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"],
    )

_init_cloudinary()


# ── Header ─────────────────────────────────────────────────────────────────────
header_col, status_col = st.columns([4, 1])
with header_col:
    st.markdown("""
    <div class="heal-header">
      <div class="heal-title">🪷 HEAL WITHIN by Aparna</div>
      <div class="heal-sub">Instagram Reel Scheduler &nbsp;·&nbsp; Where Science Meets Soul</div>
    </div>
    """, unsafe_allow_html=True)
with status_col:
    st.write("")
    st.write("")
    if st.button("🔌 Check Instagram", use_container_width=True):
        with st.spinner("Checking..."):
            r = check_connection()
        if r["connected"]:
            st.success(f"✓ @{r['username']}")
        else:
            st.error(r["message"])


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_upload, tab_queue, tab_history, tab_settings = st.tabs([
    "📤  Upload Reel",
    "⏳  Review Queue",
    "✅  Posted History",
    "⚙️  Settings & Info",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — UPLOAD
# ══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.markdown('<div class="section-title">Upload a New Reel</div>', unsafe_allow_html=True)

    with st.form("upload_form", clear_on_submit=True):
        video_file = st.file_uploader(
            "Choose your Reel video",
            type=["mp4", "mov", "avi", "m4v"],
            help="MP4 with H.264 + AAC recommended · up to 500 MB",
        )

        if video_file:
            st.video(video_file)
            size_mb = video_file.size / 1024 / 1024
            st.caption(f"📁 {video_file.name} · {size_mb:.1f} MB")

        caption = st.text_area(
            "Caption",
            placeholder="Write your healing message here...\n\nShare your heart — this is your space to inspire.",
            max_chars=2200,
            height=130,
            help="Instagram allows up to 2,200 characters",
        )
        char_col, _ = st.columns([1, 3])
        with char_col:
            st.caption(f"{len(caption)} / 2200 characters")

        hashtags = st.text_input(
            "Hashtags",
            placeholder="#HealWithin #SpiritualHealing #SelfLove #HRCM #WhereScientMeetsSoul",
            help="Separated by spaces — appended to caption automatically",
        )

        submitted = st.form_submit_button(
            "📤 Upload to Review Queue", type="primary", use_container_width=True
        )

    if submitted:
        if not video_file:
            st.error("Please select a video file.")
        elif not caption.strip():
            st.error("Please add a caption.")
        else:
            full_caption = f"{caption.strip()}\n\n{hashtags.strip()}".strip() if hashtags.strip() else caption.strip()
            if len(full_caption) > 2200:
                st.error(f"Caption + hashtags too long: {len(full_caption)}/2200 characters.")
            else:
                with st.spinner("Uploading to cloud storage..."):
                    try:
                        video_file.seek(0)
                        result = cloudinary.uploader.upload(
                            video_file.read(),
                            resource_type="video",
                            folder="heal-within-reels",
                            use_filename=True,
                            unique_filename=True,
                        )
                        add_reel(
                            filename=video_file.name,
                            caption=full_caption,
                            cloudinary_url=result["secure_url"],
                            cloudinary_public_id=result["public_id"],
                        )
                        st.success("✓ Reel uploaded! Go to **Review Queue** to approve it for posting.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REVIEW QUEUE
# ══════════════════════════════════════════════════════════════════════════════
with tab_queue:
    all_reels = get_all_reels()
    pending  = [r for r in all_reels if r["status"] == "pending"]
    approved = [r for r in all_reels if r["status"] == "approved"]
    rejected = [r for r in all_reels if r["status"] == "rejected"]

    # ── Pending approval ────────────────────────────────────────────────────
    st.markdown(
        f'<div class="section-title">⏳ Pending Approval &nbsp; <span style="color:#b09ec0;font-size:0.9rem">({len(pending)})</span></div>',
        unsafe_allow_html=True,
    )

    if not pending:
        st.info("No reels waiting for approval. Upload one on the Upload tab!")
    else:
        for reel in pending:
            with st.container(border=True):
                vid_col, info_col = st.columns([1, 2])
                with vid_col:
                    st.video(reel["cloudinary_url"])
                with info_col:
                    st.markdown('<span class="status-pending">⏳ Pending</span>', unsafe_allow_html=True)
                    created = datetime.fromisoformat(reel["created_at"].replace("Z", "+00:00"))
                    st.caption(f"Uploaded {created.strftime('%b %d, %Y  %I:%M %p')} UTC")
                    with st.expander("View full caption"):
                        st.write(reel["caption"])

                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("✓ Approve", key=f"ap_{reel['id']}", type="primary", use_container_width=True):
                            update_status(reel["id"], "approved")
                            st.success("Approved! Queued for auto-posting.")
                            st.rerun()
                    with b2:
                        if st.button("✕ Reject", key=f"rj_{reel['id']}", use_container_width=True):
                            update_status(reel["id"], "rejected")
                            st.rerun()
                    with b3:
                        if st.button("🗑 Delete", key=f"dl_{reel['id']}", use_container_width=True):
                            delete_reel(reel["id"])
                            try:
                                cloudinary.uploader.destroy(reel["cloudinary_public_id"], resource_type="video")
                            except Exception:
                                pass
                            st.rerun()

    st.divider()

    # ── Approved / scheduled ────────────────────────────────────────────────
    st.markdown(
        f'<div class="section-title">✅ Approved — Queued for Auto-Posting &nbsp; <span style="color:#b09ec0;font-size:0.9rem">({len(approved)})</span></div>',
        unsafe_allow_html=True,
    )

    if not approved:
        st.info("No approved reels yet. Approve a reel above to schedule it.")
    else:
        for i, reel in enumerate(approved):
            with st.container(border=True):
                vid_col, info_col = st.columns([1, 2])
                with vid_col:
                    st.video(reel["cloudinary_url"])
                with info_col:
                    st.markdown('<span class="status-approved">✅ Approved</span>', unsafe_allow_html=True)
                    if i == 0:
                        st.markdown("🎯 **Next in line** — posts at your scheduled time today")
                    created = datetime.fromisoformat(reel["created_at"].replace("Z", "+00:00"))
                    st.caption(f"Approved since {created.strftime('%b %d, %Y')}")

                    with st.expander("View full caption"):
                        st.write(reel["caption"])

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("📤 Post Now", key=f"pn_{reel['id']}", type="primary", use_container_width=True):
                            ph = st.empty()
                            def _cb(msg, _ph=ph):
                                _ph.info(f"⏳ {msg}")
                            with st.spinner("Posting to Instagram… this takes 1–5 minutes"):
                                result = post_reel(reel["cloudinary_url"], reel["caption"], status_callback=_cb)
                            ph.empty()
                            if result["success"]:
                                update_status(reel["id"], "posted")
                                st.success(f"🎉 Posted! Instagram ID: {result['ig_id']}")
                                st.rerun()
                            else:
                                st.error(f"Failed: {result['error']}")
                    with b2:
                        if st.button("🗑 Remove", key=f"rm_{reel['id']}", use_container_width=True):
                            delete_reel(reel["id"])
                            try:
                                cloudinary.uploader.destroy(reel["cloudinary_public_id"], resource_type="video")
                            except Exception:
                                pass
                            st.rerun()

    # ── Rejected (collapsed) ────────────────────────────────────────────────
    if rejected:
        st.divider()
        with st.expander(f"❌ Rejected ({len(rejected)})"):
            for reel in rejected:
                with st.container(border=True):
                    vc, ic = st.columns([1, 2])
                    with vc:
                        st.video(reel["cloudinary_url"])
                    with ic:
                        st.write(reel["caption"][:120] + "…")
                        if st.button("↩ Re-approve", key=f"ra_{reel['id']}", use_container_width=True):
                            update_status(reel["id"], "approved")
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    all_reels = get_all_reels()
    posted = [r for r in all_reels if r["status"] == "posted"]

    st.markdown(
        f'<div class="section-title">🌟 Posted Reels &nbsp; <span style="color:#b09ec0;font-size:0.9rem">({len(posted)})</span></div>',
        unsafe_allow_html=True,
    )

    if not posted:
        st.info("No reels have been posted yet. Your history will appear here after the first post.")
    else:
        cols = st.columns(3)
        for i, reel in enumerate(posted):
            with cols[i % 3]:
                with st.container(border=True):
                    st.video(reel["cloudinary_url"])
                    if reel.get("posted_at"):
                        dt = datetime.fromisoformat(reel["posted_at"].replace("Z", "+00:00"))
                        st.caption(f"Posted {dt.strftime('%b %d, %Y')}")
                    st.markdown('<span class="status-posted">✅ Posted</span>', unsafe_allow_html=True)
                    with st.expander("Caption"):
                        st.write(reel["caption"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SETTINGS & INFO
# ══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    left, right = st.columns(2)

    with left:
        st.markdown('<div class="section-title">📱 Instagram Connection</div>', unsafe_allow_html=True)
        if st.button("🔌 Test Connection", use_container_width=True):
            with st.spinner("Testing..."):
                r = check_connection()
            if r["connected"]:
                st.success(f"✓ Connected as **@{r['username']}** — {r['name']}")
                if r.get("ig_id"):
                    st.info(f"📋 Your correct INSTAGRAM_USER_ID is: **{r['ig_id']}**")
            else:
                st.error(f"✗ {r['message']}")

        st.markdown('<div class="section-title" style="margin-top:24px">🕐 Auto-Post Schedule</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
          <b style="color:#D4AF37">⏰ 9:00 AM Calgary (MDT) every day</b><br>
          <span style="color:#b09ec0;font-size:0.85rem">
            GitHub Actions runs the daily cron job at 15:00 UTC (= 9 AM MDT).<br>
            To change the time, edit <code>.github/workflows/daily_poster.yml</code>
            — look for the <code>cron:</code> line and adjust using
            <a href="https://crontab.guru" target="_blank" style="color:#D4AF37">crontab.guru</a>.
          </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title" style="margin-top:24px">📊 Queue Stats</div>', unsafe_allow_html=True)
        all_r = get_all_reels()
        c1, c2, c3 = st.columns(3)
        c1.metric("Pending",  len([r for r in all_r if r["status"] == "pending"]))
        c2.metric("Approved", len([r for r in all_r if r["status"] == "approved"]))
        c3.metric("Posted",   len([r for r in all_r if r["status"] == "posted"]))

    with right:
        st.markdown('<div class="section-title">🔑 Instagram API Setup Guide</div>', unsafe_allow_html=True)
        with st.expander("Step-by-step — get your access token", expanded=True):
            st.markdown("""
**1. Create a Meta Developer App**
- Go to [developers.facebook.com](https://developers.facebook.com)
- Create a **Business** type app
- Add the **Instagram Graph API** product

**2. Connect your Instagram account**
- Under *Instagram → Instagram Accounts*
- Connect your **Business or Creator** account

**3. Get required permissions**
```
instagram_basic
instagram_content_publish
pages_read_engagement
```

**4. Generate a long-lived token** (valid 60 days)
- Use Graph API Explorer → get short-lived token
- Exchange it via the token exchange endpoint

**5. Find your Instagram User ID**
```
GET /me?fields=id,name&access_token=YOUR_TOKEN
```

**6. Add secrets to Streamlit Cloud**
App Settings → Secrets → paste `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_USER_ID`
            """)

    st.divider()
    st.markdown('<div class="section-title">📦 One-Time Setup Checklist</div>', unsafe_allow_html=True)
    ca, cb = st.columns(2)
    with ca:
        st.markdown("""
**Streamlit Cloud Secrets** *(App Settings → Secrets)*
- `SUPABASE_URL`
- `SUPABASE_KEY` *(service_role key)*
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`
- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`
        """)
    with cb:
        st.markdown("""
**GitHub Actions Secrets** *(Repo → Settings → Secrets → Actions)*
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`

**Supabase** *(SQL Editor — run once)*
- Paste and run `supabase_setup.sql`
        """)
