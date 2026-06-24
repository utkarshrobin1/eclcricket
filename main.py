import os
import io
import time
import random
import asyncio
import urllib.request
import urllib.error
import struct
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ChatMemberHandler, filters,
    ContextTypes, TypeHandler
)
from motor.motor_asyncio import AsyncIOMotorClient

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not installed. Team scoreboard image generation disabled.")
    print("Install with: pip install Pillow")

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
load_dotenv()
TOKEN      = os.getenv("BOT_TOKEN")
MONGO_URI  = os.getenv("MONGO_URI")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT       = int(os.environ.get("PORT", "8080"))

OWNER_IDS = [8828369268]

LOG_GROUP_ID = -1004483580256

# Path to the scoreboard template image (1536x1024).
# Place the template PNG next to this script named scoreboard_template.png,
# OR set SCOREBOARD_TEMPLATE_URL to the remote image URL.
SCOREBOARD_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "scoreboard_template.png"
)
SCOREBOARD_TEMPLATE_URL = os.getenv(
    "SCOREBOARD_TEMPLATE_URL",
    "https://res.cloudinary.com/dxgfxfoog/image/upload/v1778123859/scoreboard_template.png"
)

# New scoreboard template with host/captain pfp circles.
# Place scoreboard_template_v2.png next to this script,
# OR set SCOREBOARD_TEMPLATE_V2_URL to the remote image URL.
SCOREBOARD_TEMPLATE_V2_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "scoreboard_template_v2.png"
)
SCOREBOARD_TEMPLATE_V2_URL = os.getenv(
    "SCOREBOARD_TEMPLATE_V2_URL",
    "https://res.cloudinary.com/dxgfxfoog/image/upload/v1780030720379/file_00000000279c7207a79334a845b2e823.png"
)

# POTM (Player of the Match) card template.
# Place potm_template.png next to this script, OR set POTM_TEMPLATE_URL.
POTM_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "potm_template.png"
)
POTM_TEMPLATE_URL = os.getenv("POTM_TEMPLATE_URL", "")

# User Stats card template.
# Place userstats_template.jpg next to this script, OR set USERSTATS_TEMPLATE_URL.
USERSTATS_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "userstats_template.jpg"
)
USERSTATS_TEMPLATE_URL = os.getenv(
    "USERSTATS_TEMPLATE_URL",
    "https://res.cloudinary.com/dxgfxfoog/image/upload/userstats_template.jpg"
)

# Font used for the user stats card image.
USERSTATS_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fonts", "PWBoldScript.ttf"
)

# ---------------------------------------------------------------------------
# MongoDB Setup
# ---------------------------------------------------------------------------
try:
    _mongo_client    = AsyncIOMotorClient(MONGO_URI)
    db               = _mongo_client["cricket_bot_db"]
    users_col        = db["users"]
    chats_col        = db["interacted_chats"]
    tournaments_col  = db["tournaments"]
    tourteams_col    = db["tour_teams"]
    media_cache_col  = db["media_cache"]
    banned_users_col    = db["banned_users"]
    match_history_col   = db["match_history"]
    permitted_hosts_col = db["permitted_hosts"]
except Exception as e:
    print(f"MongoDB Connection Error: {e}")
    users_col           = None
    chats_col           = None
    tournaments_col     = None
    tourteams_col       = None
    media_cache_col     = None
    banned_users_col    = None
    match_history_col   = None
    permitted_hosts_col = None

# ---------------------------------------------------------------------------
# Media URLs
# ---------------------------------------------------------------------------
MEDIA = {
    "batter_turn": "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777818927/VID_20260503195533_zt4tux.mp4",
    "bowler_turn": "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777694389/VID_20260502092829_np7h5d.mp4",
    "out":         "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777641612/1777641553346_zexrt4.mp4",
    "duck":        "https://media.giphy.com/media/krewXUB6LBja/giphy.gif",
    "50":          "https://media.giphy.com/media/07oir8PhvSReDNpNi7/giphy.gif",
    "100":         "https://media.giphy.com/media/pR0jymbIr7HrrpISUW/giphy.gif",
    "yorker":      "https://media.giphy.com/media/2CUJFvoRXDrUeG1mOS/giphy.gif",
    0: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777717596/VID_20260502_155429_102_xtppvn.mp4",
    1: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777642218/animation.gif_1_u1ksyt.mp4",
    2: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777642586/VID_20260501_190546_668_tdnzth.mp4",
    3: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777642484/VID_20260501_190413_260_cylqql.mp4",
    4: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777644250/VID_20260501_193031_696_quwh5m.mp4",
    5: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777642378/VID_20260501_190216_576_yonoc2.mp4",
    6: "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777818980/VID_20260503195551_qcyvct.mp4",
}

# Static scoreboard image used for SOLO mode (and as fallback)
SCOREBOARD_IMG   = "https://res.cloudinary.com/dxgfxfoog/image/upload/v1777876839/file_000000001fc07207a39f861ace603999_tjaafo.png"
TEAMS_ROSTER_IMG = "https://res.cloudinary.com/dxgfxfoog/image/upload/v1779771065/IMG_20260526_101925_753_wd5eyl.jpg"

# ---------------------------------------------------------------------------
# Commentary lines shown after batter hits (runs scored)
# ---------------------------------------------------------------------------
# Commentary keyed by exact runs scored — context-aware, not random noise
HIT_COMMENTARY = {
    0: [
        "🛡️ DOT BALL! The bowler wins this battle — pressure is building!",
        "😤 Tight line and length! The batter had absolutely no answer!",
        "🔒 Beats the bat! The bowler is looking dangerous right now!",
        "😬 Played and missed! That was agonisingly close!",
        "🎯 Pinpoint accuracy! The batter is stuck in a web here!",
        "💪 Great delivery! The batter played and missed — bowler on top!",
        "🤫 Silence from the bat! The bowler wins the mind game!",
        "😅 Survived, but barely! That kept low and almost crept through!",
        "🧱 Defended well, but the bowler is absolutely controlling this spell!",
        "📉 Pressure mounting... The batter needs to find a way through!",
        "🎯 Another dot! The bowler is squeezing every last run out!",
        "😰 The batter's in trouble! Nothing is coming off the middle of the bat!",
    ],
    1: [
        "🏃 Quick single! Smart cricket — keep rotating that strike!",
        "👣 One and running! Great awareness from the batter!",
        "🏏 Nudged away for one — keeping the scoreboard ticking nicely!",
        "1️⃣ Just a single, but in cricket every run is priceless!",
        "🔄 Good placement for one! Batter retains strike intelligently!",
        "📊 Sensible cricket — take the single, don't throw it away!",
        "🎯 Dropped it into the gap and sneaks a single — smart play!",
        "🧠 One run, no fuss. Accumulate, accumulate, accumulate!",
        "👏 Working it around — the batter knows exactly what they're doing!",
        "💡 Cool head, smart single. This batter is crafty out there!",
        "🏃‍♂️ They run hard! Every run counts when you're chasing a total!",
        "🤝 Partnership building run by run — the batter is ice-cold!",
    ],
    2: [
        "✌️ TWO RUNS! Brilliant placement through the gap!",
        "🏃‍♂️ Running hard between the wickets — 2 sweet runs!",
        "🎯 Found the gap! The fielders are scrambling!",
        "💨 Pushed through the covers — 2 beautiful runs picked up!",
        "2️⃣ Two! Great running and even better shot selection!",
        "😮 Perfect timing! Skips through for a couple — great cricket!",
        "🔥 Two more on the board! The batter is building a knock here!",
        "📈 Scoreboard moving! 2 runs and the momentum shifts slightly!",
        "⚡ Quick between the wickets — 2 runs taken with ease!",
        "🏏 Guided it beautifully for 2 — elegant stroke play!",
        "💎 Two! The batter finds the gap the fielder couldn't cover!",
        "🎶 Poetic placement for 2! The batter is reading the field perfectly!",
    ],
    3: [
        "🔥 THREE RUNS! Brilliant running converts it to a maximum non-boundary!",
        "💪 Great effort — THREE taken! Excellent work between the wickets!",
        "😱 THREE! They kept on running and the fielder fumbled — DISASTER for the fielding side!",
        "3️⃣ Outstanding running! 3 runs — you can't ask for more from a ground shot!",
        "🏃 Superb athleticism between the wickets — 3 runs! That's world-class fitness!",
        "🎉 Three runs! The batter is putting the fielding team under massive pressure!",
        "🔥 They ran THREE! Aggressive, smart, fearless cricket!",
        "⚡ Three! The fielding side is absolutely furious by that effort run!",
        "💨 THREEEE! What running, what shot selection — this batter is something else!",
        "🏆 That's world-class running — 3 hard-earned, fully-deserved runs!",
        "🌟 Three! The batter has the fielding team chasing shadows!",
        "🎯 Excellent placement and even better running — 3 runs on the board!",
    ],
    4: [
        "🏏 FOUR! 💥 Absolutely SMASHED through the covers! What a shot!",
        "🔥 BOUNDARY! The ball races to the fence — nobody could stop it!",
        "💥 FOUR! The fielder didn't even move — completely beaten all ends up!",
        "🎯 FOUR! Perfect placement, impossible to stop — textbook stroke!",
        "😍 FOUR! That is a BEAUTY of a shot — right out of the coaching manual!",
        "⚡ FOUR! The crowd is on their feet — what a moment!",
        "🏆 FOUR! That shot alone was worth the price of admission!",
        "💨 FOUR! Screams through the infield — the fielders had no chance!",
        "🌟 What TIMING! FOUR! The bat did ALL the talking there!",
        "🎪 FOUR! The bowler watches in sheer disbelief!",
        "🔥 FOUR ALL THE WAY! Pure, unadulterated class from the batter!",
        "🏏 Cut shot! FOUR! The batter is absolutely in BEAST MODE right now!",
        "💎 That's a gem of a four! Effortless elegance at its finest!",
        "😤 FOUR! The batter said ENOUGH and put it away with AUTHORITY!",
        "🚀 FOUR! That was hit so sweetly it barely made a sound off the bat!",
    ],
    5: [
        "5️⃣ FIVE RUNS! Incredible shot combined with brilliant running — what a moment!",
        "💥 FIVE! Overthrows added insult to injury — disaster for the fielders!",
        "😱 FIVEEE! That's extraordinary — the batter is absolutely loving every second of this!",
        "🔥 Five! Once in a while you witness cricket like this — soak it in!",
        "🚀 FIVEEE! The crowd cannot believe what they're watching!",
        "🌟 Five runs! The fielding side is in absolute chaos out there!",
        "🏆 FIVE! Everything went right for the batter and wrong for the fielders!",
    ],
    6: [
        "💥 SIX! 🚀 GONE! RIGHT OUT OF THE STADIUM — GONE FOR GOOD!",
        "🏏 MAXIMUM! 💥 The ball is STILL FLYING through the air!",
        "🔥 SIX! The bowler can only watch in pure AGONY as it clears the rope!",
        "🌟 SIXXXX! That's deep into the stands — what an INCREDIBLE hit!",
        "😱 SIX! Pure raw MUSCLE! The crowd has gone completely INSANE!",
        "🎯 MAXIMUM! Picked it up from outside off and LAUNCHED it into orbit!",
        "👑 SIX! That is absolutely DISRESPECTFUL to the bowling — MONSTROUS HIT!",
        "🚀 SIXXX! That has LEFT THE BUILDING! Absolutely RIDICULOUS power!",
        "💫 SIX! Over long-on! The batter is officially in total GODMODE right now!",
        "🎆 SIX! BOOM! It's fireworks time! What a MAGNIFICENT SHOT!",
        "⚡ SIX! Hit it SO hard the bowler could feel it in their bones!",
        "🏆 MAXIMUM! The batter has absolutely MURDERED that ball — no mercy!",
        "🌪️ SIX! The bat connected SO sweetly — an absolute THUNDERBOLT of a hit!",
        "😤 SIX! The batter looked up and said I'M HITTING THIS ONE TO THE MOON!",
        "🎪 6 hai bhai Gend  faad di Bowlers ki 🎀",
    ],
}

# ---------------------------------------------------------------------------
# Scoreboard Pillow image (TEAM mode only)
# ---------------------------------------------------------------------------
# Template coordinates are for a 1536×1024 image.
# Adjust these if your template has different dimensions.
_SB = {
    # Circle at top-centre (group logo or "LIVE" text)
    "circle_cx": 768,  "circle_cy": 205,  "circle_r": 140,

    # Team A — score text centre, overs text centre
    "team_a_score_cx": 453, "team_a_score_cy": 640,
    "team_a_overs_cx": 453, "team_a_overs_cy": 673,

    # Team B — score text centre, overs text centre
    "team_b_score_cx": 1083, "team_b_score_cy": 640,
    "team_b_overs_cx": 1083, "team_b_overs_cy": 673,

    # Bottom bar value rows  (one y for all four)
    "bar_y":          900,
    "innings_cx":     192,
    "crr_cx":         576,
    "bowler_cx":      960,
    "batter_cx":     1344,
}

_FONT_PATHS = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

# ---------------------------------------------------------------------------
# Coordinates for the new V2 scoreboard template (with pfp circles).
# Template image is ~1080×760 — adjust values if your template differs.
# ---------------------------------------------------------------------------
# Percentage-based coords for V2 template — works for any image dimensions.
# All values are fractions of (image_width, image_height, image_width).
# Tweak these if you swap the template for one with different circle positions.
# ---------------------------------------------------------------------------
_SB_V2 = {
    # Host pfp circle at the top-centre  (auto-detected from template)
    "host_cx_pct":  0.4974, "host_cy_pct":  0.1172, "host_r_pct":  0.0302,
    # Team A captain pfp (red / left side)
    "cap_a_cx_pct": 0.2897, "cap_a_cy_pct": 0.5059, "cap_a_r_pct": 0.0924,
    # Team B captain pfp (blue / right side)
    "cap_b_cx_pct": 0.7057, "cap_b_cy_pct": 0.5068, "cap_b_r_pct": 0.0924,
}

_template_cache: bytes | None = None
_template_v2_cache: bytes | None = None
_potm_template_cache: bytes | None = None
_userstats_template_cache: bytes | None = None

# In-memory cache of the composited (template + pfp circles) image per chat.
# Key: chat_id  →  {"key": (host_id, cap_a_id, cap_b_id), "bytes": <PNG bytes>}
_scoreboard_pfp_cache: dict = {}


def _load_font(size: int):
    """Load a bold font at the given size, falling back to PIL default."""
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _get_template_bytes() -> bytes | None:
    """Return raw bytes of the template PNG (cached after first load)."""
    global _template_cache
    if _template_cache is not None:
        return _template_cache

    # 1. Try local file first
    if os.path.exists(SCOREBOARD_TEMPLATE_PATH):
        try:
            with open(SCOREBOARD_TEMPLATE_PATH, "rb") as f:
                _template_cache = f.read()
            return _template_cache
        except Exception as exc:
            print(f"[scoreboard] Failed to read local template: {exc}")

    # 2. Try remote URL
    try:
        req = urllib.request.Request(
            SCOREBOARD_TEMPLATE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            _template_cache = resp.read()
        return _template_cache
    except Exception as exc:
        print(f"[scoreboard] Failed to download template: {exc}")

    return None


async def _fetch_group_photo_bytes(context, chat_id: int) -> bytes | None:
    """Attempt to download the group profile photo. Returns bytes or None."""
    try:
        chat = await context.bot.get_chat(chat_id)
        if not chat.photo:
            return None
        file = await chat.photo.get_big_file()
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        return None


def _get_template_v2_bytes() -> bytes | None:
    """Return raw bytes of the V2 template PNG (cached after first load)."""
    global _template_v2_cache
    if _template_v2_cache is not None:
        return _template_v2_cache
    if os.path.exists(SCOREBOARD_TEMPLATE_V2_PATH):
        try:
            with open(SCOREBOARD_TEMPLATE_V2_PATH, "rb") as f:
                _template_v2_cache = f.read()
            return _template_v2_cache
        except Exception as exc:
            print(f"[scoreboard_v2] Failed to read local template: {exc}")
    if SCOREBOARD_TEMPLATE_V2_URL:
        try:
            req = urllib.request.Request(
                SCOREBOARD_TEMPLATE_V2_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                _template_v2_cache = resp.read()
            return _template_v2_cache
        except Exception as exc:
            print(f"[scoreboard_v2] Failed to download template: {exc}")
    return None


def _get_potm_template_bytes() -> bytes | None:
    """Return raw bytes of the POTM card template PNG (cached after first load)."""
    global _potm_template_cache
    if _potm_template_cache is not None:
        return _potm_template_cache
    if os.path.exists(POTM_TEMPLATE_PATH):
        try:
            with open(POTM_TEMPLATE_PATH, "rb") as f:
                _potm_template_cache = f.read()
            return _potm_template_cache
        except Exception as exc:
            print(f"[potm] Failed to read local template: {exc}")
    if POTM_TEMPLATE_URL:
        try:
            req = urllib.request.Request(
                POTM_TEMPLATE_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                _potm_template_cache = resp.read()
            return _potm_template_cache
        except Exception as exc:
            print(f"[potm] Failed to download template: {exc}")
    return None


async def _fetch_user_photo_bytes(context, user_id: int) -> bytes | None:
    """Download the profile photo of a Telegram user. Returns bytes or None."""
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if not photos or not photos.photos:
            return None
        file = await photos.photos[0][-1].get_file()
        buf = io.BytesIO()
        await file.download_to_memory(buf)
        return buf.getvalue()
    except Exception:
        return None


def _get_userstats_template_bytes() -> bytes | None:
    """Return raw bytes of the userstats card template (cached after first load)."""
    global _userstats_template_cache
    if _userstats_template_cache is not None:
        return _userstats_template_cache
    if os.path.exists(USERSTATS_TEMPLATE_PATH):
        try:
            with open(USERSTATS_TEMPLATE_PATH, "rb") as f:
                _userstats_template_cache = f.read()
            return _userstats_template_cache
        except Exception as exc:
            print(f"[userstats] Failed to read local template: {exc}")
    if USERSTATS_TEMPLATE_URL:
        try:
            req = urllib.request.Request(
                USERSTATS_TEMPLATE_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                _userstats_template_cache = resp.read()
            return _userstats_template_cache
        except Exception as exc:
            print(f"[userstats] Failed to download template: {exc}")
    return None


# ---------------------------------------------------------------------------
# User Stats card coordinates  (for 1500×1000 template).
# All _pct values are fractions of image width/height so any size works.
# ---------------------------------------------------------------------------
_US = {
    # Profile-picture circle (top-left white circle)
    "pfp_cx_pct": 0.1067,   # cx ≈ 160
    "pfp_cy_pct": 0.1050,   # cy ≈ 105
    "pfp_r_pct":  0.0633,   # r  ≈  95

    # Value text centre-x (right-side blue box, horizontal midpoint)
    "val_cx_pct": 0.7300,   # cx ≈ 1095

    # 9 data rows — vertical centre of each value box (fraction of height)
    "row_cy_pcts": [
        0.251,   # TOTAL RUNS
        0.334,   # HIGHEST RUNS
        0.417,   # BATTING AVG
        0.500,   # DUCKS
        0.583,   # TOTAL 50s
        0.666,   # TOTAL 100s
        0.749,   # TOTAL WICKETS
        0.832,   # CAREER ECONOMY
        0.915,   # HATTRICKS
    ],

    # Row height fraction (used to size the font so text nearly fills the box)
    "row_h_pct": 0.083,
}


def _load_userstats_font(size: int):
    """Load PWBoldScript.ttf at *size*, fall back to bold system font."""
    if os.path.exists(USERSTATS_FONT_PATH):
        try:
            return ImageFont.truetype(USERSTATS_FONT_PATH, size)
        except Exception:
            pass
    return _load_font(size)


async def generate_userstats_image(
    context,
    user_id: int,
    total_runs: int,
    hs_runs: int,
    hs_balls: int,
    avg: float,
    ducks: int,
    half_centuries: int,
    centuries: int,
    wickets: int,
    eco: float,
    hat_tricks: int,
) -> bytes | None:
    """
    Compose the userstats card template with the user's pfp in the circle
    and their stats drawn in each value box.
    Returns PNG bytes or None on failure.
    """
    if not PIL_AVAILABLE:
        return None

    template_bytes = await asyncio.to_thread(_get_userstats_template_bytes)
    if template_bytes is None:
        return None

    photo_bytes = await _fetch_user_photo_bytes(context, user_id)

    try:
        img  = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
        iw, ih = img.size
        draw = ImageDraw.Draw(img)

        # ── Profile picture circle ──────────────────────────────────────────
        cx = int(iw * _US["pfp_cx_pct"])
        cy = int(ih * _US["pfp_cy_pct"])
        r  = int(iw * _US["pfp_r_pct"])

        if photo_bytes:
            pfp  = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
            pw, ph = pfp.size
            side = min(pw, ph)
            pfp  = pfp.crop(((pw - side) // 2, (ph - side) // 2,
                              (pw + side) // 2, (ph + side) // 2))
            pfp  = pfp.resize((r * 2, r * 2), Image.LANCZOS)
            mask = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            img.paste(pfp, (cx - r, cy - r), mask)

        # ── Stat values ─────────────────────────────────────────────────────
        val_cx   = int(iw * _US["val_cx_pct"])
        row_h    = int(ih * _US["row_h_pct"])
        # Target font size: fill ~75% of row height so text nearly touches borders
        font_size = max(10, int(row_h * 0.75))
        font      = _load_userstats_font(font_size)

        hs_text  = f"{hs_runs} ({hs_balls}b)" if hs_balls > 0 else str(hs_runs)
        avg_text = f"{avg:.2f}"
        eco_text = f"{eco:.2f}"

        values = [
            str(total_runs),
            hs_text,
            avg_text,
            str(ducks),
            str(half_centuries),
            str(centuries),
            str(wickets),
            eco_text,
            str(hat_tricks),
        ]

        row_cy_pcts = _US["row_cy_pcts"]
        for i, val_str in enumerate(values):
            row_cy = int(ih * row_cy_pcts[i])
            bbox   = draw.textbbox((0, 0), val_str, font=font)
            tw     = bbox[2] - bbox[0]
            th     = bbox[3] - bbox[1]
            tx     = val_cx - tw // 2
            ty     = row_cy - th // 2
            # Drop shadow for readability
            draw.text((tx + 2, ty + 2), val_str, font=font, fill=(0, 0, 0, 160))
            draw.text((tx, ty),         val_str, font=font, fill=(255, 255, 255, 255))

        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as exc:
        print(f"[userstats] generate_userstats_image error: {exc}")
        return None


def _paste_circle_photo(img: "Image.Image", photo_bytes: bytes,
                         cx: int, cy: int, r: int) -> None:
    """Paste photo_bytes as a circular crop centred at (cx, cy) with radius r."""
    if not PIL_AVAILABLE or photo_bytes is None:
        return
    try:
        pfp = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
        pfp = pfp.resize((r * 2, r * 2), Image.LANCZOS)
        mask = Image.new("L", (r * 2, r * 2), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.ellipse((0, 0, r * 2, r * 2), fill=255)
        img.paste(pfp, (cx - r, cy - r), mask)
    except Exception as exc:
        print(f"[scoreboard_v2] _paste_circle_photo error: {exc}")


async def build_scoreboard_base_image(context, chat_id: int, game: dict) -> bytes | None:
    """
    Compose the V2 template with host + captain profile photos and cache it.
    Returns PNG bytes of the base image, or None on failure.
    Cached in _scoreboard_pfp_cache per chat, invalidated when host/captains change.
    """
    if not PIL_AVAILABLE:
        return None

    host_id  = game.get("host_id")
    cap_a_id = game.get("team_a", {}).get("captain")
    cap_b_id = game.get("team_b", {}).get("captain")
    cache_key = (host_id, cap_a_id, cap_b_id)

    cached = _scoreboard_pfp_cache.get(chat_id)
    if cached and cached.get("key") == cache_key and cached.get("bytes"):
        return cached["bytes"]

    template_bytes = await asyncio.to_thread(_get_template_v2_bytes)
    if template_bytes is None:
        return None

    host_photo, cap_a_photo, cap_b_photo = await asyncio.gather(
        _fetch_user_photo_bytes(context, host_id)  if host_id  else asyncio.sleep(0),
        _fetch_user_photo_bytes(context, cap_a_id) if cap_a_id else asyncio.sleep(0),
        _fetch_user_photo_bytes(context, cap_b_id) if cap_b_id else asyncio.sleep(0),
    )

    try:
        img = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
        iw, ih = img.size  # actual template dimensions

        # Compute pixel coordinates from percentages so any template size works
        host_cx  = int(iw * _SB_V2["host_cx_pct"])
        host_cy  = int(ih * _SB_V2["host_cy_pct"])
        host_r   = int(iw * _SB_V2["host_r_pct"])
        cap_a_cx = int(iw * _SB_V2["cap_a_cx_pct"])
        cap_a_cy = int(ih * _SB_V2["cap_a_cy_pct"])
        cap_a_r  = int(iw * _SB_V2["cap_a_r_pct"])
        cap_b_cx = int(iw * _SB_V2["cap_b_cx_pct"])
        cap_b_cy = int(ih * _SB_V2["cap_b_cy_pct"])
        cap_b_r  = int(iw * _SB_V2["cap_b_r_pct"])

        if isinstance(host_photo, bytes):
            _paste_circle_photo(img, host_photo,  host_cx,  host_cy,  host_r)
        if isinstance(cap_a_photo, bytes):
            _paste_circle_photo(img, cap_a_photo, cap_a_cx, cap_a_cy, cap_a_r)
        if isinstance(cap_b_photo, bytes):
            _paste_circle_photo(img, cap_b_photo, cap_b_cx, cap_b_cy, cap_b_r)

        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        result = buf.getvalue()

        _scoreboard_pfp_cache[chat_id] = {"key": cache_key, "bytes": result}
        return result
    except Exception as exc:
        print(f"[scoreboard_v2] build_scoreboard_base_image error: {exc}")
        return None


def _invalidate_scoreboard_pfp_cache(chat_id: int) -> None:
    """Remove the cached base scoreboard image for a chat so it rebuilds next time."""
    _scoreboard_pfp_cache.pop(chat_id, None)


def _draw_centered_text(draw: "ImageDraw.ImageDraw", cx: int, cy: int,
                         text: str, font, fill=(255, 255, 255),
                         shadow: bool = True):
    """Draw text centred at (cx, cy) with an optional drop-shadow."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = cx - w // 2
    y = cy - h // 2
    if shadow:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font, fill=fill)


async def generate_team_scoreboard_image(context, chat_id: int, game: dict) -> bytes | None:
    """
    Return the V2 scoreboard image (template + host/captain pfp circles).
    The score data is sent as the Telegram caption, not drawn on the image.
    Uses build_scoreboard_base_image() which caches the result per chat.
    Only called in TEAM mode.
    """
    return await build_scoreboard_base_image(context, chat_id, game)


# ---------------------------------------------------------------------------
# POTM card image coordinates (percentage-based, works for any template size).
# Inner circle = blank area inside the golden ring where the pfp is placed.
# Name box    = the horizontal panel at the bottom where the player name goes.
# ---------------------------------------------------------------------------
_POTM = {
    "circle_cx_pct": 0.720,   # X centre — right-side white circle (new template)
    "circle_cy_pct": 0.492,   # Y centre — new template
    "circle_r_pct":  0.170,   # radius — fills inner white area of the ring
}


async def generate_potm_image(context, potm_name: str, potm_id: int) -> bytes | None:
    """
    Compose the POTM card template with the player's pfp (or initial-letter
    fallback) clipped into the right-side white circle.
    Returns PNG bytes or None on failure. Player name is NOT drawn on the image.
    """
    if not PIL_AVAILABLE:
        return None

    template_bytes = await asyncio.to_thread(_get_potm_template_bytes)
    if template_bytes is None:
        return None

    photo_bytes = await _fetch_user_photo_bytes(context, potm_id)

    try:
        img  = Image.open(io.BytesIO(template_bytes)).convert("RGBA")
        iw, ih = img.size
        draw = ImageDraw.Draw(img)

        cx = int(iw * _POTM["circle_cx_pct"])
        cy = int(ih * _POTM["circle_cy_pct"])
        r  = int(iw * _POTM["circle_r_pct"])

        if photo_bytes:
            # ── Paste pfp as a perfect circular crop filling the inner circle ──
            pfp   = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
            pw, ph = pfp.size
            # Centre-crop to square so the face isn't stretched
            side  = min(pw, ph)
            left  = (pw - side) // 2
            top   = (ph - side) // 2
            pfp   = pfp.crop((left, top, left + side, top + side))
            pfp   = pfp.resize((r * 2, r * 2), Image.LANCZOS)
            mask  = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            img.paste(pfp, (cx - r, cy - r), mask)
        else:
            # ── No pfp — draw a solid circle with the player's first initial ──
            initial   = (potm_name[0].upper() if potm_name else "?")
            bg_layer  = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
            bg_draw   = ImageDraw.Draw(bg_layer)
            bg_draw.ellipse((0, 0, r * 2, r * 2), fill=(20, 75, 170, 255))
            mask      = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            img.paste(bg_layer, (cx - r, cy - r), mask)
            # Draw the initial centred in the circle
            init_font = _load_font(int(r * 0.95))
            ibbox     = draw.textbbox((0, 0), initial, font=init_font)
            iw2, ih2  = ibbox[2] - ibbox[0], ibbox[3] - ibbox[1]
            draw.text(
                (cx - iw2 // 2 + 1, cy - ih2 // 2 + 1),
                initial, font=init_font, fill=(0, 0, 0, 120)
            )
            draw.text(
                (cx - iw2 // 2, cy - ih2 // 2),
                initial, font=init_font, fill=(255, 255, 255, 255)
            )

        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as exc:
        print(f"[potm] generate_potm_image error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def get_user_level(exp: int) -> str:
    if exp < 1000:
        return "Newbie 🔰"
    elif exp <= 5000:
        return "Pro ⚡"
    elif exp <= 8000:
        return "Legendary 🌟"
    elif exp <= 13000:
        return "Unbeaten 👑"
    elif exp <= 26000:
        return "Aura Farmer 🔱"
    else:
        return "God ☯️"


def get_next_level_info(exp: int):
    if exp < 1000:
        return "Pro ⚡", 1000 - exp
    elif exp <= 5000:
        return "Legendary 🌟", 5001 - exp
    elif exp <= 8000:
        return "Unbeaten 👑", 8001 - exp
    elif exp <= 13000:
        return "Aura Farmer 🔱", 13001 - exp
    elif exp <= 26000:
        return "God ☯️", 26001 - exp
    else:
        return None, 0


async def global_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if chats_col is not None and update.effective_chat:
        try:
            title = update.effective_chat.title or "Private/Unknown"
            now_ts = int(time.time())
            await chats_col.update_one(
                {"chat_id": update.effective_chat.id},
                {"$set": {
                    "chat_id": update.effective_chat.id,
                    "type": update.effective_chat.type,
                    "title": title,
                    "last_active": now_ts,
                }},
                upsert=True,
            )
        except Exception:
            pass
    if users_col is not None and update.effective_user:
        try:
            now_ts = int(time.time())
            await users_col.update_one(
                {"user_id": update.effective_user.id},
                {"$set": {"last_seen": now_ts}},
            )
        except Exception:
            pass


async def track_bot_kicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    if result.new_chat_member.status in ["left", "kicked"]:
        if chats_col is not None:
            await chats_col.delete_one({"chat_id": chat.id})
    elif result.new_chat_member.status in ["member", "administrator"]:
        if chats_col is not None:
            title = chat.title or "Group"
            await chats_col.update_one(
                {"chat_id": chat.id},
                {"$set": {"chat_id": chat.id, "type": chat.type, "title": title}},
                upsert=True,
            )


async def send_media_safely(context, chat_id, media_url, caption,
                             reply_markup=None, reply_to_message_id=None):
    # Try to use cached file_id from MongoDB first
    cached_file_id   = None
    cached_media_type = None
    if media_cache_col is not None and media_url:
        try:
            cached = await media_cache_col.find_one({"url": media_url})
            if cached:
                cached_file_id    = cached.get("file_id")
                cached_media_type = cached.get("media_type")
        except Exception:
            pass

    try:
        if cached_file_id and cached_media_type:
            if cached_media_type == "animation":
                await context.bot.send_animation(
                    chat_id=chat_id, animation=cached_file_id, caption=caption,
                    parse_mode="HTML", reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id,
                    read_timeout=8, write_timeout=8,
                )
            elif cached_media_type == "photo":
                await context.bot.send_photo(
                    chat_id=chat_id, photo=cached_file_id, caption=caption,
                    parse_mode="HTML", reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id,
                    read_timeout=8, write_timeout=8,
                )
            else:
                await context.bot.send_video(
                    chat_id=chat_id, video=cached_file_id, caption=caption,
                    parse_mode="HTML", reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id,
                    read_timeout=8, write_timeout=8,
                )
        elif media_url.endswith(".gif") or "giphy.com" in media_url:
            await context.bot.send_animation(
                chat_id=chat_id, animation=media_url, caption=caption,
                parse_mode="HTML", reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                read_timeout=8, write_timeout=8,
            )
        else:
            await context.bot.send_video(
                chat_id=chat_id, video=media_url, caption=caption,
                parse_mode="HTML", reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                read_timeout=8, write_timeout=8,
            )
    except Exception as e:
        print(f"Failed to send media {media_url}: {e}. Using fallback.")
        fallback = f"<a href='{media_url}'>&#8205;</a>{caption}"
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=fallback, parse_mode="HTML",
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
            )
        except Exception as e2:
            print(f"Fallback failed: {e2}")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def init_user_db(user_id, first_name, username):
    if users_col is None:
        return
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        await users_col.insert_one({
            "user_id": user_id, "first_name": first_name, "username": username,
            "exp": 0, "weekly_runs": 0, "weekly_wickets": 0,
            "weekly_conceded": 0, "weekly_balls_bowled": 0, "weekly_balls_faced": 0,
            "highest_score": {"runs": 0, "balls": 0},
            "total_runs": 0, "balls_faced": 0,
            "solo_matches": 0, "team_matches": 0,
            "total_6s": 0, "total_4s": 0,
            "centuries": 0, "half_centuries": 0, "ducks": 0,
            "balls_bowled": 0, "runs_conceded": 0, "wickets": 0,
            "motm": 0, "hat_tricks": 0, "catches": 0,
        })
    else:
        update_fields = {}
        if user.get("first_name") != first_name:
            update_fields["first_name"] = first_name
        if username and user.get("username") != username:
            update_fields["username"] = username
        if update_fields:
            await users_col.update_one({"user_id": user_id}, {"$set": update_fields})


async def update_user_db(user_id, updates):
    if users_col is None:
        return
    await users_col.update_one({"user_id": user_id}, {"$inc": updates}, upsert=True)


async def update_highest_score(user_id, runs, balls):
    if users_col is None:
        return
    user = await users_col.find_one({"user_id": user_id})
    if user and runs > user.get("highest_score", {}).get("runs", 0):
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"highest_score": {"runs": runs, "balls": balls}}},
        )


async def update_match_played(players, mode):
    if users_col is None:
        return
    field = "solo_matches" if mode == "SOLO" else "team_matches"
    for p in players:
        await update_user_db(p["id"], {field: 1})


async def is_permitted_host(user_id: int) -> bool:
    """Return True if user_id is an active permitted host (lifetime or not yet expired)."""
    if permitted_hosts_col is None:
        return False
    try:
        doc = await permitted_hosts_col.find_one({"user_id": user_id})
        if not doc:
            return False
        expires = doc.get("expires")
        if expires is None:
            return True  # lifetime permit
        return time.time() < expires
    except Exception:
        return False


async def is_banned(user_id: int) -> bool:
    """Return True if user_id is in the banned list."""
    if banned_users_col is None:
        return False
    try:
        doc = await banned_users_col.find_one({"user_id": user_id})
        return doc is not None
    except Exception:
        return False


_RANK1_CATEGORIES = [
    ("total_runs",      "🏃 Total Runs",      "runs"),
    ("wickets",         "🥎 Wickets",          "wickets"),
    ("total_6s",        "💥 Sixes",            "sixes"),
    ("centuries",       "💯 Centuries",        "centuries"),
    ("half_centuries",  "🌟 Half-Centuries",   "half-centuries"),
    ("hat_tricks",      "🎩 Hat-Tricks",       "hat-tricks"),
    ("catches",         "🧤 Catches",          "catches"),
]


async def commit_player_stats(game):
    if users_col is None:
        return
    if game.get("mode") != "TEAM":
        players = game.get("players", [])
    else:
        team_a = game.get("team_a", {}).get("players", [])
        team_b = game.get("team_b", {}).get("players", [])
        players = team_a + team_b

    for p in players:
        runs       = p.get("runs", 0)
        balls_faced = p.get("balls_faced", 0)
        await update_highest_score(p["id"], runs, balls_faced)
        updates = {
            "total_runs": runs,
            "balls_faced": balls_faced,
            "balls_bowled": p.get("balls_bowled", 0),
            "runs_conceded": p.get("conceded", 0),
            "wickets": p.get("wickets", 0),
            "total_4s": p.get("match_4s", 0),
            "total_6s": p.get("match_6s", 0),
            "catches": p.get("catches", 0),
            "weekly_runs": runs,
            "weekly_balls_faced": balls_faced,
            "weekly_balls_bowled": p.get("balls_bowled", 0),
            "weekly_conceded": p.get("conceded", 0),
            "weekly_wickets": p.get("wickets", 0),
        }
        if runs == 0 and p.get("is_out", False):
            updates["ducks"] = 1
        if runs >= 100:
            updates["centuries"] = 1
        elif runs >= 50:
            updates["half_centuries"] = 1
        await update_user_db(p["id"], updates)

    await update_match_played(players, game.get("mode", "SOLO"))
    potm = get_potm_data(game)
    if potm:
        await update_user_db(potm["id"], {"motm": 1})


def get_potm_data(game):
    best_player = None
    best_score  = -999
    if game.get("mode") != "TEAM":
        players = game.get("players", [])
    else:
        players = (
            game.get("team_a", {}).get("players", [])
            + game.get("team_b", {}).get("players", [])
        )
    for p in players:
        score = p.get("runs", 0) + (p.get("wickets", 0) * 15) - (p.get("conceded", 0) * 0.5)
        if score > best_score:
            best_score  = score
            best_player = p
    return best_player


# ---------------------------------------------------------------------------
# Game-state utilities
# ---------------------------------------------------------------------------

async def is_admin(chat, user_id):
    try:
        admins = await chat.get_administrators()
        for admin in admins:
            if admin.user.id == user_id:
                return True
        return False
    except Exception:
        try:
            member = await chat.get_member(user_id)
            return member.status in ["administrator", "creator"]
        except Exception:
            return False


def get_next_num(players):
    nums = [p["num"] for p in players if "num" in p]
    i = 1
    while i in nums:
        i += 1
    return i


def is_user_playing_anywhere(context, user_id):
    for cid, data in context.bot_data.items():
        if not isinstance(data, dict):
            continue
        if data.get("state") in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
            continue
        if any(p.get("id") == user_id for p in data.get("players", [])):
            return True
        if "team_a" in data and any(
            p.get("id") == user_id for p in data.get("team_a", {}).get("players", [])
        ):
            return True
        if "team_b" in data and any(
            p.get("id") == user_id for p in data.get("team_b", {}).get("players", [])
        ):
            return True
    return False


def get_user_from_mention(update):
    target_user     = None
    target_username = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    else:
        for entity in (update.message.entities or []):
            if entity.type == "text_mention":
                target_user = entity.user
                break
            elif entity.type == "mention":
                target_username = (
                    update.message.text[entity.offset: entity.offset + entity.length]
                    .lstrip("@")
                    .lower()
                )
                break
    return target_user, target_username


def dismiss_batter(game, batter):
    batter["is_out"]        = True
    batter["is_striker"]    = False
    batter["is_non_striker"] = False
    if game.get("striker") and game["striker"]["id"] == batter["id"]:
        game["striker"] = None
    if game.get("non_striker") and game["non_striker"]["id"] == batter["id"]:
        game["non_striker"] = None


def swap_strike(game):
    st = game.get("striker")
    ns = game.get("non_striker")
    if st and ns:
        game["striker"]  = ns
        game["non_striker"] = st
        game["striker"]["is_striker"]      = True
        game["striker"]["is_non_striker"]  = False
        game["non_striker"]["is_striker"]  = False
        game["non_striker"]["is_non_striker"] = True
    elif st and not ns:
        game["non_striker"] = st
        game["striker"]     = None
        game["non_striker"]["is_non_striker"] = True
        game["non_striker"]["is_striker"]     = False
    elif ns and not st:
        game["striker"]   = ns
        game["non_striker"] = None
        game["striker"]["is_striker"]     = True
        game["striker"]["is_non_striker"] = False


# ---------------------------------------------------------------------------
# Scorecard text generation
# ---------------------------------------------------------------------------

def generate_scorecard(game):
    if game.get("mode") == "TEAM":
        return generate_team_scorecard(game)

    players = game.get("players", [])
    batter_idx = game.get("batter_idx", 0)
    bowler_idx = game.get("bowler_idx", 0)
    state = game.get("state", "")

    text = (
        "🌀━━━━━━━━\n"
        "<b>⚡SOLO SCORECARD</b>\n"
        "           ━━━━━━━━🌀\n\n"
    )

    for i, p in enumerate(players):

        runs = p.get("runs", 0)
        balls = p.get("balls_faced", 0)
        sr = (runs / balls * 100) if balls else 0

        balls_bowled = p.get("balls_bowled", 0)
        overs, rem = divmod(balls_bowled, 6)

        conceded = p.get("conceded", 0)
        wkts = p.get("wickets", 0)

        eco = (
            (conceded / balls_bowled) * 6
            if balls_bowled else 0
        )

        # Status icon
        if p.get("is_out"):
            status = "❌"
        elif state == "PLAYING" and i == batter_idx:
            status = "🏏"
        elif state == "PLAYING" and i == bowler_idx:
            status = "🥎"
        else:
            status = "⏳"

        text += (
            f"👤 <b>{p['name']}</b> {status}\n"
            f"├ 🏏 {runs}({balls}) | SR {sr:.1f}\n"
            f"├ 🥎 {wkts}W | {conceded}R | "
            f"{overs}.{rem}ov | Eco {eco:.1f}\n"
        )

        # Spell system
        is_cur_bowler = (
            state == "PLAYING" and i == bowler_idx
        )

        spells = list(p.get("bowling_spells", []))

        if (
            is_cur_bowler and
            p.get("_spell_balls0") is not None
        ):

            lb = (
                p.get("balls_bowled", 0)
                - p["_spell_balls0"]
            )

            lr = (
                p.get("conceded", 0)
                - p["_spell_runs0"]
            )

            lw = (
                p.get("wickets", 0)
                - p["_spell_wkts0"]
            )

            if lb > 0:
                spells.append({
                    "b": lb,
                    "r": lr,
                    "w": lw,
                    "live": True
                })

        if spells:

            for idx, s in enumerate(spells, 1):

                ov, bl = divmod(s["b"], 6)

                line = (
                    f"Spell{idx} | "
                    f"{ov}.{bl}ov | "
                    f"{s['r']}R | "
                    f"{s['w']}W"
                )

                if idx == 1:
                    text += f"└ 📋 {line}\n"
                elif idx == len(spells):
                    text += f"   └ {line}\n"
                else:
                    text += f"   ├ {line}\n"

        else:
            text += "└ 📋 No spells\n"

        text += "\n"

    text += "\n\n#elite_bots"

    return text




def generate_team_scorecard(game):

    striker = game.get("striker") or {}
    non_striker = game.get("non_striker") or {}
    current_bowler = game.get("current_bowler") or {}

    innings = game.get("innings", 1)

    is_finished = game.get(
        "state"
    ) in ["TEAM_FINISHED", "NOT_PLAYING"]

    text = (
        "🌀━━━━━━━━\n"
        "<b>⚡TEAM SCORECARD</b>\n"
        "           ━━━━━━━━🌀\n\n"
    )

    # ===== RESULT =====

    if is_finished:

        a = game.get(
            "team_a", {}
        ).get("score", 0)

        b = game.get(
            "team_b", {}
        ).get("score", 0)

        if a > b:

            bat_ref = game.get(
                "batting_team_ref"
            )

            if bat_ref is game.get(
                "team_a"
            ):

                wkts_left = (
                    len(
                        game["team_a"]["players"]
                    ) - 1
                ) - game["team_a"]["wickets"]

                wkts_left = max(
                    0,
                    wkts_left
                )

                text += (
                    "🏆 TEAM A WON\n"
                    f"📈 BY {wkts_left} WICKET"
                    f"{'S' if wkts_left != 1 else ''}\n\n"
                )

            else:

                diff = a - b

                text += (
                    "🏆 TEAM A WON\n"
                    f"📈 BY {diff} RUN"
                    f"{'S' if diff != 1 else ''}\n\n"
                )

        elif b > a:

            bat_ref = game.get(
                "batting_team_ref"
            )

            if bat_ref is game.get(
                "team_b"
            ):

                wkts_left = (
                    len(
                        game["team_b"]["players"]
                    ) - 1
                ) - game["team_b"]["wickets"]

                wkts_left = max(
                    0,
                    wkts_left
                )

                text += (
                    "🏆 TEAM B WON\n"
                    f"📈 BY {wkts_left} WICKET"
                    f"{'S' if wkts_left != 1 else ''}\n\n"
                )

            else:

                diff = b - a

                text += (
                    "🏆 TEAM B WON\n"
                    f"📈 BY {diff} RUN"
                    f"{'S' if diff != 1 else ''}\n\n"
                )

        else:

            text += (
                "🤝 MATCH TIED\n"
                "🔥 WHAT A THRILLER\n\n"
            )

    # ===== CHASE INFO =====

    elif innings == 2:

        target = game.get(
            "target", 0
        )

        batting_team = game.get(
            "batting_team_ref", {}
        )

        bowling_team = game.get(
            "bowling_team_ref", {}
        )

        current_score = batting_team.get(
            "score", 0
        )

        runs_needed = max(
            0,
            target - current_score
        )

        balls_total = game.get(
            "target_overs",
            game.get("overs", 5)
        ) * 6

        balls_used = bowling_team.get(
            "balls_bowled", 0
        )

        balls_left = max(
            0,
            balls_total - balls_used
        )

        rrr = (
            (runs_needed / balls_left) * 6
            if balls_left > 0
            else 0
        )

        text += (
            f"🎯 Chase | Target {target}\n"
            f"📉 Need {runs_needed} in {balls_left} balls\n"
            f"⚡ RRR | {rrr:.2f}\n\n"
        )

    # ===== TEAM SECTIONS =====

    for team_key, emoji in [

        ("team_a", "🔴"),
        ("team_b", "🔵")

    ]:

        team = game.get(
            team_key, {}
        )

        opp_key = (
            "team_b"
            if team_key == "team_a"
            else "team_a"
        )

        opp_team = game.get(
            opp_key, {}
        )

        balls = opp_team.get(
            "balls_bowled", 0
        )

        ov, rem = divmod(
            balls, 6
        )

        rr = (
            team.get("score", 0)
            / (balls / 6)
            if balls > 0 else 0
        )

        wickets = team.get(
            "wickets", 0
        )

        title = (
            "TEAM A"
            if team_key == "team_a"
            else "TEAM B"
        )

        text += (
            "✦ ─────────────────── ✦\n"
            f"{emoji} <b>{title}</b> | "
            f"{team.get('score',0)}/{wickets}\n"
            f"└ {ov}.{rem}ov | RR {rr:.2f}\n\n"
        )

        # ===== PLAYERS =====

        for p in team.get(
            "players", []
        ):

            show_player = (

                p.get(
                    "balls_faced", 0
                ) > 0

                or p.get(
                    "balls_bowled", 0
                ) > 0

                or p.get("is_out")

                or p.get("id")
                == striker.get("id")

                or p.get("id")
                == non_striker.get("id")

            )

            if not show_player:
                continue

            runs = p.get(
                "runs", 0
            )

            balls_faced = p.get(
                "balls_faced", 0
            )

            sr = (
                runs / balls_faced * 100
                if balls_faced > 0
                else 0
            )

            balls_bowled = p.get(
                "balls_bowled", 0
            )

            overs, rem2 = divmod(
                balls_bowled,
                6
            )

            conceded = p.get(
                "conceded", 0
            )

            wkts = p.get(
                "wickets", 0
            )

            eco = (
                (conceded / balls_bowled) * 6
                if balls_bowled else 0
            )

            # Status icon

            if p.get("is_out"):
                status = "❌"

            elif p.get("id") == striker.get("id"):
                status = "⚡"

            elif p.get("id") == non_striker.get("id"):
                status = "🏃"

            elif p.get("id") == current_bowler.get("id"):
                status = "🎯"

            else:
                status = "⏳"

            text += (
                f"👤 <b>{p['name']}</b> {status}\n"
                f"├ 🏏 {runs}({balls_faced}) "
                f"| SR {sr:.0f}\n"
            )

            if balls_bowled > 0:

                text += (
                    f"├ 🥎 {wkts}W | "
                    f"{conceded}R | "
                    f"{overs}.{rem2}ov | "
                    f"Eco {eco:.1f}\n"
                )

            else:

                text += (
                    "├ 🥎 No bowling data\n"
                )

            # ===== SPELLS =====

            spells = list(
                p.get(
                    "bowling_spells",
                    []
                )
            )

            if spells:

                for idx, s in enumerate(
                    spells,
                    1
                ):

                    ov2, bl2 = divmod(
                        s["b"],
                        6
                    )

                    line = (
                        f"Spell{idx} | "
                        f"{ov2}.{bl2}ov | "
                        f"{s['r']}R | "
                        f"{s['w']}W"
                    )

                    if idx == 1:

                        text += (
                            f"└ 📋 {line}\n"
                        )

                    elif idx == len(spells):

                        text += (
                            f"   └ {line}\n"
                        )

                    else:

                        text += (
                            f"   ├ {line}\n"
                        )

            else:

                text += (
                    "└ 📋 No spell data\n"
                )

            text += "\n"

    text += "\n#elite_bots"

    return text

            


def get_potm(game):

    best = get_potm_data(game)

    if not best:
        return "Unknown"

    best_name = best.get(
        "name",
        "Unknown"
    )

    # keep telegram names from breaking UI
    if len(best_name) > 12:
        best_name = (
            best_name[:12]
            + "..."
        )

    return best_name

def get_potm_message(game):

    best = get_potm_data(game)

    if not best:
        return "", 0

    best_name = best.get("name", "Unknown")
    best_id   = best.get("id", 0)

    return best_name, best_id


def generate_teams_message(game):
    text = "🏟️ <b>TEAMS ROSTER</b> 🏟️\n\n"
    is_playing = game.get("state") == "PLAYING"
    bat_team   = game.get("batting_team_ref", {}) if is_playing else {}
    bowl_team  = game.get("bowling_team_ref", {}) if is_playing else {}

    for team_key, team_dict in [("team_a", game.get("team_a", {})), ("team_b", game.get("team_b", {}))]:
        team_name = "🔴 <b>TEAM A</b>" if team_key == "team_a" else "🔵 <b>TEAM B</b>"
        text += f"{team_name}\n"
        for i, p in enumerate(team_dict.get("players", []), 1):
            cap    = " (C) 👑" if team_dict.get("captain") == p["id"] else ""
            status = ""
            if is_playing:
                if team_dict is bat_team:
                    if p.get("is_out"):
                        status = " - (Out)"
                    elif p.get("is_striker"):
                        status = " - (On Strike)"
                    elif p.get("is_non_striker"):
                        status = " - (Non Striker)"
                    else:
                        status = " - (yet to bat)"
                elif team_dict is bowl_team:
                    cb = game.get("current_bowler") or {}
                    if cb.get("id") == p["id"]:
                        status = " - (Bowling)"
            pid = p["id"]; pname = p["name"]; text += f" {p.get('num', i)}. <a href='tg://user?id={pid}'>{pname}</a>{cap}<i>{status}</i>\n"
        text += "\n"
    return text


# ---------------------------------------------------------------------------
# Scorecard sender — PILLOW image for TEAM mode, static image for SOLO
# ---------------------------------------------------------------------------

async def trigger_full_scorecard_message(context: ContextTypes.DEFAULT_TYPE,
                                          chat_id: int, game_data: dict):
    scorecard  = generate_scorecard(game_data)
    final_text = scorecard
    _is_finished = game_data.get("state") in ["NOT_PLAYING", "TEAM_FINISHED"]

    markup = None
    if game_data.get("state") in ["NOT_PLAYING", "TEAM_FINISHED"]:
        bot_info = await context.bot.get_me()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("PLAY AGAIN 🔄", callback_data="play_again")],
            [InlineKeyboardButton("ADD IN GROUP ➕", url=f"https://t.me/{bot_info.username}?startgroup=true")],
        ])

    # Telegram caps photo captions at 1024 characters.
    # Split into image + separate text message if needed.
    MAX_CAPTION = 1024
    use_separate_text = len(final_text) > MAX_CAPTION

    if game_data.get("mode") == "TEAM":
        # Generate custom Pillow scoreboard image
        img_bytes = await generate_team_scoreboard_image(context, chat_id, game_data)
        _team_sent = False
        if img_bytes:
            try:
                if use_separate_text:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=io.BytesIO(img_bytes),
                        caption="📊 <b>TEAM SCORECARD</b> — see details below.",
                        parse_mode="HTML",
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=final_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=io.BytesIO(img_bytes),
                        caption=final_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                _team_sent = True
            except Exception as e:
                print(f"[scoreboard] Failed to send Pillow image: {e}")
                # Fall through to static image fallback

        if not _team_sent:
            # Pillow unavailable or failed — use static image fallback
            try:
                if use_separate_text:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=SCOREBOARD_IMG,
                        caption="📊 <b>TEAM SCORECARD</b> — see details below.",
                        parse_mode="HTML",
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=final_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=SCOREBOARD_IMG,
                        caption=final_text,
                        parse_mode="HTML",
                        reply_markup=markup,
                    )
            except Exception as e:
                print(f"[scoreboard] Fallback photo also failed: {e}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=final_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
    else:
        # SOLO mode — use static image
        try:
            if use_separate_text:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=SCOREBOARD_IMG,
                    caption="📊 <b>SCORECARD</b> — see details below.",
                    parse_mode="HTML",
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=final_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=SCOREBOARD_IMG,
                    caption=final_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        except Exception as e:
            print(f"[scoreboard] Solo photo failed: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=final_text,
                parse_mode="HTML",
                reply_markup=markup,
            )

    # ── Send POTM card image (with caption) after final scorecard ─────────
    if _is_finished:
        try:
            _potm_data = get_potm_data(game_data)
            if _potm_data:
                _potm_name = _potm_data.get("name", "Unknown")
                _potm_id   = _potm_data.get("id", 0)
                _potm_runs = _potm_data.get("runs", 0)
                _potm_wkts = _potm_data.get("wickets", 0)
                _potm_link = f"<a href='tg://user?id={_potm_id}'>{_potm_name}</a>"
                _potm_captions = [
                    (
                        f"🏅 <b>PLAYER OF THE MATCH</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🌟 {_potm_link} — here's your reward, take this💋\n\n"
                        f"🏏 <b>{_potm_runs} runs</b> &amp; 🥎 <b>{_potm_wkts} wickets</b> — absolutely elite!\n"
                        f"You stepped up when it mattered most and dominated. Pure class! 🔥👑"
                    ),
                    (
                        f"🏅 <b>PLAYER OF THE MATCH — {_potm_name.upper()}</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🔥 {_potm_link} was UNSTOPPABLE today!\n\n"
                        f"📊 <b>{_potm_runs} runs · {_potm_wkts} wickets</b>\n"
                        f"A masterclass performance! The arena bows to you, champion! 🏆👏"
                    ),
                    (
                        f"🌟 <b>OUTSTANDING PERFORMANCE!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} takes <b>Player of the Match!</b>\n\n"
                        f"💥 <b>{_potm_runs} runs</b> smashed with the bat 🏏\n"
                        f"⚡ <b>{_potm_wkts} wickets</b> taken with the ball 🥎\n"
                        f"This is what legends are made of! Keep flying! 🦅🔥"
                    ),
                    (
                        f"👑 <b>HALL OF FAME MOMENT!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} — <b>Player of the Match!</b>\n\n"
                        f"<b>{_potm_runs} runs · {_potm_wkts} wickets</b>\n"
                        f"The crowd goes wild! What a special player you are. 🎊🏆"
                    ),
                    (
                        f"🔥 <b>ELITE LEVEL PERFORMANCE!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"{_potm_link} — tonight's undisputed <b>PLAYER OF THE MATCH!</b> 🏅\n\n"
                        f"🏏 <b>{_potm_runs} runs</b> — bat on fire!\n"
                        f"🥎 <b>{_potm_wkts} wickets</b> — bowling was lethal!\n"
                        f"This one is going in the history books. 📖👑"
                    ),
                    (
                        f"🏅 <b>PLAYER OF THE MATCH</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🎯 {_potm_link} — YOU are the reason we play this game!\n\n"
                        f"💪 <b>{_potm_runs} runs &amp; {_potm_wkts} wickets</b>\n"
                        f"Delivered under pressure, stayed calm, and made history. 🔥🙌"
                    ),
                    (
                        f"🎉 <b>MAGNIFICENT DISPLAY!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} clinches <b>Player of the Match!</b>\n\n"
                        f"📊 <b>{_potm_runs}</b> runs off the bat | <b>{_potm_wkts}</b> wickets in hand\n"
                        f"Not just a player — a MATCH WINNER. Respect! 💯🔥"
                    ),
                    (
                        f"⚡ <b>MATCH WINNER ALERT!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} — <b>Player of the Match!</b>\n\n"
                        f"🏏 <b>{_potm_runs} runs</b> — batting at its finest!\n"
                        f"🥎 <b>{_potm_wkts} wickets</b> — bowling masterclass!\n"
                        f"Single-handedly carried the team today. What a legend! 🦁🏆"
                    ),
                    (
                        f"🌟 <b>STAR PERFORMER OF THE DAY</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} — everyone, give a round of applause! 👏\n\n"
                        f"<b>{_potm_runs} runs</b> &amp; <b>{_potm_wkts} wickets</b> — a complete performance!\n"
                        f"Elite Cricket Bot salutes you, champion! 🎖️🔥"
                    ),
                    (
                        f"🏅 <b>PLAYER OF THE MATCH</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"👑 {_potm_link} — the definition of match-winning cricket!\n\n"
                        f"🔥 <b>{_potm_runs} runs</b> smashed | <b>{_potm_wkts} wickets</b> claimed\n"
                        f"When the team needed a hero, you answered. Bow down! 🙇‍♂️🏆"
                    ),
                    (
                        f"💎 <b>DIAMOND PERFORMANCE!</b>\n━━━━━━━━━━━━━━━━\n\n"
                        f"🏅 {_potm_link} — <b>Player of the Match — undisputed!</b>\n\n"
                        f"🏏 <b>{_potm_runs} runs</b> with the bat 🔥\n"
                        f"🥎 <b>{_potm_wkts} wickets</b> with the ball ⚡\n"
                        f"All-round excellence. You are BUILT DIFFERENT. 💪👑"
                    ),
                ]
                _potm_caption = random.choice(_potm_captions)
                _potm_img_bytes = await generate_potm_image(context, _potm_name, _potm_id)
                if _potm_img_bytes:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=io.BytesIO(_potm_img_bytes),
                        caption=_potm_caption,
                        parse_mode="HTML",
                    )
                else:
                    # Template not available — fall back to plain text
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=_potm_caption,
                        parse_mode="HTML",
                    )
        except Exception:
            pass



async def send_top_performers_message(context: ContextTypes.DEFAULT_TYPE,
                                       chat_id: int, game: dict):
    text = "🌟 <b>TOP PERFORMERS OF THE MATCH</b> 🌟\n━━━━━━━━━━━━━━━━\n"
    for team_key, team_name in [("team_a", "🔴 TEAM A"), ("team_b", "🔵 TEAM B")]:
        team = game.get(team_key)
        if not team or not team.get("players"):
            continue
        best_batter = max(team["players"], key=lambda x: x.get("runs", 0))
        best_bowler = max(
            team["players"],
            key=lambda x: x.get("wickets", 0) * 100 - x.get("conceded", 0),
        )
        text += f"\n<b>{team_name}</b>\n"
        text += (
            f"🏏 <b>Best Batter:</b> {best_batter['name'][:15]} ➜ "
            f"<b>{best_batter.get('runs', 0)}</b> ({best_batter.get('balls_faced', 0)})\n"
        )
        b_ov, b_bl = divmod(best_bowler.get("balls_bowled", 0), 6)
        text += (
            f"🥎 <b>Best Bowler:</b> {best_bowler['name'][:15]} ➜ "
            f"<b>{best_bowler.get('wickets', 0)}W</b> for {best_bowler.get('conceded', 0)}R "
            f"({b_ov}.{b_bl} Ov)\n"
        )
    text += "\n━━━━━━━━━━━━━━━\n"
    await context.bot.send_message(chat_id, text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# AFK system
# ---------------------------------------------------------------------------

def set_afk_timer(context, chat_id, user_id, role):
    clear_afk_timer(context, chat_id)
    game = context.bot_data.get(chat_id)
    if not game:
        return
    if game.get("mode") == "TEAM":
        context.job_queue.run_once(team_afk_warning_10, 10,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk10_{chat_id}")
        context.job_queue.run_once(team_afk_warning_30, 30,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk30_{chat_id}")
        context.job_queue.run_once(team_afk_timeout,    60,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk60_{chat_id}")
    else:
        context.job_queue.run_once(afk_warning_start,   10,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk10_{chat_id}")
        context.job_queue.run_once(afk_warning_30,      30,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk30_{chat_id}")
        context.job_queue.run_once(afk_timeout,         60,  data={"chat_id": chat_id, "user_id": user_id, "role": role}, name=f"afk60_{chat_id}")


def clear_afk_timer(context, chat_id):
    for prefix in ["afk1_", "afk10_", "afk30_", "afk60_", "afk90_"]:
        for job in context.job_queue.get_jobs_by_name(f"{prefix}{chat_id}"):
            job.schedule_removal()


async def check_solo_winner_exp(game):
    if game.get("mode") == "SOLO" and game.get("players"):
        best = max(game["players"], key=lambda x: x.get("runs", 0))
        await update_user_db(best["id"], {"exp": 60})


async def save_match_history_to_db(context, chat_id: int, game: dict):
    if match_history_col is None:
        return
    try:
        mode = game.get("mode", "SOLO")
        record = {
            "chat_id":   chat_id,
            "timestamp": time.time(),
            "mode":      mode,
            "overs":     game.get("target_overs", game.get("overs", "?")),
        }
        if mode == "SOLO":
            players = game.get("players", [])
            best    = max(players, key=lambda x: x.get("runs", 0)) if players else {}
            record["winner_name"] = best.get("name", "Unknown")
            record["winner_runs"] = best.get("runs", 0)
            record["players"] = [
                {
                    "name":        p["name"],
                    "id":          p["id"],
                    "runs":        p.get("runs", 0),
                    "balls_faced": p.get("balls_faced", 0),
                    "wickets":     p.get("wickets", 0),
                    "balls_bowled":p.get("balls_bowled", 0),
                    "match_4s":    p.get("match_4s", 0),
                    "match_6s":    p.get("match_6s", 0),
                    "is_out":      p.get("is_out", False),
                }
                for p in players
            ]
        else:
            team_a   = game.get("team_a", {})
            team_b   = game.get("team_b", {})
            a_score  = team_a.get("score", 0)
            b_score  = team_b.get("score", 0)
            if a_score > b_score:
                record["winner_team"] = "team_a"
            elif b_score > a_score:
                record["winner_team"] = "team_b"
            else:
                record["winner_team"] = "tie"
            record["target"]    = game.get("target", 0)
            # Save POTM for history display
            potm = get_potm_data(game)
            if potm:
                record["motm_name"]    = potm.get("name", "?")
                record["motm_runs"]    = potm.get("runs", 0)
                record["motm_wickets"] = potm.get("wickets", 0)
            host_id             = game.get("host_id")
            all_p               = team_a.get("players", []) + team_b.get("players", [])
            record["host_name"] = next((p["name"] for p in all_p if p["id"] == host_id), "Unknown")
            for key, team in [("team_a", team_a), ("team_b", team_b)]:
                cap_id = team.get("captain")
                record[key] = {
                    "score":    team.get("score", 0),
                    "wickets":  team.get("wickets", 0),
                    "captain":  next((p["name"] for p in team.get("players", []) if p["id"] == cap_id), "?"),
                    "players": [
                        {
                            "name":        p["name"],
                            "id":          p["id"],
                            "runs":        p.get("runs", 0),
                            "balls_faced": p.get("balls_faced", 0),
                            "wickets":     p.get("wickets", 0),
                            "balls_bowled":p.get("balls_bowled", 0),
                            "match_4s":    p.get("match_4s", 0),
                            "match_6s":    p.get("match_6s", 0),
                        }
                        for p in team.get("players", [])
                    ],
                }
        await match_history_col.insert_one(record)
        # Keep only last 5 per chat — delete older ones
        old_docs = await match_history_col.find(
            {"chat_id": chat_id}, {"_id": 1}
        ).sort("timestamp", -1).skip(5).to_list(length=1000)
        if old_docs:
            await match_history_col.delete_many(
                {"_id": {"$in": [d["_id"] for d in old_docs]}}
            )
    except Exception as e:
        print(f"Match history save error: {e}")


# ── Solo AFK ────────────────────────────────────────────────────────────────

async def afk_warning_start(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return
    player = next((p for p in game.get("players", []) if p["id"] == user_id), None)
    if not player:
        return
    await context.bot.send_message(
        chat_id,
        f"⚠️ <a href='tg://user?id={user_id}'>{player['name']}</a>, "
        "it is your turn! You have <b>50 seconds</b> to play. ⏳",
        parse_mode="HTML",
    )


async def afk_warning_30(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return
    player = next((p for p in game.get("players", []) if p["id"] == user_id), None)
    if not player:
        return
    await context.bot.send_message(
        chat_id,
        f"⚠️ <a href='tg://user?id={user_id}'>{player['name']}</a>, "
        "HURRY UP! You only have <b>30 seconds</b> left to play! ⏰",
        parse_mode="HTML",
    )


async def afk_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return

    player = next((p for p in game.get("players", []) if p["id"] == user_id), None)
    if not player:
        return

    await context.bot.send_message(
        chat_id,
        f"⏳ <b>TIME'S UP!</b> {player['name']} was AFK for 60 seconds and has been ELIMINATED! ❌",
        parse_mode="HTML",
    )

    elim_idx = next(
        (i for i, p in enumerate(game.get("players", [])) if p["id"] == user_id), -1
    )
    if elim_idx == -1:
        return
    game["players"] = [p for p in game["players"] if p["id"] != user_id]

    if len(game["players"]) < 2:
        await commit_player_stats(game)
        game["state"] = "NOT_PLAYING"
        await context.bot.send_message(chat_id, "Not enough players left! Match abandoned. 🛑", parse_mode="HTML")
        return

    if elim_idx < game["batter_idx"]:
        game["batter_idx"] -= 1

    if game["batter_idx"] >= len(game["players"]):
        await check_solo_winner_exp(game)
        await commit_player_stats(game)
        game["state"] = "NOT_PLAYING"
        await context.bot.send_message(chat_id, "🏁 <b>MATCH FINISHED! \nHarne wale pe sab hasenge, sabse pehle mai hasunga 😂😂</b> 🏁", parse_mode="HTML")
        await trigger_full_scorecard_message(context, chat_id, game)
        return

    available_bowlers = [i for i in range(len(game["players"])) if i != game["batter_idx"]]
    if available_bowlers:
        game["bowler_idx"] = random.choice(available_bowlers)
    else:
        await commit_player_stats(game)
        game["state"] = "NOT_PLAYING"
        await context.bot.send_message(chat_id, "Not enough players left! Match abandoned. 🛑", parse_mode="HTML")
        return

    game["waiting_for"]           = "BOWLER"
    game["balls_bowled"]          = 0
    game["special_used_this_over"] = False
    await trigger_bowl(context, chat_id)


# ── Team AFK ─────────────────────────────────────────────────────────────────

async def team_afk_warning_10(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return
    all_players = game.get("team_a", {}).get("players", []) + game.get("team_b", {}).get("players", [])
    player = next((p for p in all_players if p["id"] == user_id), None)
    if not player:
        return
    await context.bot.send_message(
        chat_id,
        f"⚠️ <a href='tg://user?id={user_id}'>{player['name']}</a>, "
        "you have been AFK! You have <b>50 more seconds</b> left to play. ⏳",
        parse_mode="HTML",
    )


async def team_afk_warning_30(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return
    all_players = game.get("team_a", {}).get("players", []) + game.get("team_b", {}).get("players", [])
    player = next((p for p in all_players if p["id"] == user_id), None)
    if not player:
        return
    await context.bot.send_message(
        chat_id,
        f"⚠️ <a href='tg://user?id={user_id}'>{player['name']}</a>, "
        "HURRY UP! You only have <b>30 seconds</b> left to play! ⏰",
        parse_mode="HTML",
    )


async def team_afk_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, user_id, role = job.data["chat_id"], job.data["user_id"], job.data["role"]
    game = context.bot_data.get(chat_id)
    waiting = game.get("waiting_for", "") if game else ""
    role_match = (waiting == role) or (role == "BATTER" and waiting == "PROCESSING_BATTER")
    if not game or game.get("state") != "PLAYING" or not role_match:
        return

    all_players = game.get("team_a", {}).get("players", []) + game.get("team_b", {}).get("players", [])
    player = next((p for p in all_players if p["id"] == user_id), None)
    if not player:
        return

    if role == "BATTER":
        dismiss_batter(game, player)
        game["batting_team_ref"]["score"]   = max(0, game["batting_team_ref"]["score"] - 5)
        player["runs"]                       = max(0, player.get("runs", 0) - 5)
        game["batting_team_ref"]["wickets"] += 1
        await context.bot.send_message(
            chat_id,
            f"⏳ <b>TIME'S UP!</b> {player['name']} was AFK for 60 seconds! ❌\n"
            "📉 <b>PENALTY:</b> -5 Runs to the team and batter! They are OUT!",
            parse_mode="HTML",
        )
        if game["batting_team_ref"]["wickets"] >= len(game["batting_team_ref"]["players"]) - 1:
            await process_team_innings_end(context, chat_id, game)
            return
        game["waiting_for"] = "TEAM_BATTER_SELECT"
        await context.bot.send_message(
            chat_id,
            "🏏 Captain/Host, please select the next batter using <code>/batting [number]</code>.",
            parse_mode="HTML",
        )
    elif role == "BOWLER":
        game["batting_team_ref"]["score"] += 5
        player["conceded"] = player.get("conceded", 0) + 5
        await context.bot.send_message(
            chat_id,
            f"⏳ <b>TIME'S UP!</b> {player['name']} timed out! ❌\n"
            "📈 <b>PENALTY:</b> +5 Runs to Batting Team!\n"
            "Captain/Host, please select a NEW bowler to continue the over using "
            "<code>/bowling [number]</code>.",
            parse_mode="HTML",
        )
        if game.get("innings") == 2 and game["batting_team_ref"]["score"] >= game.get("target", 0):
            await process_team_innings_end(context, chat_id, game)
            return
        game["waiting_for"]  = "TEAM_BOWLER_SELECT"
        game["last_bowler_id"] = player["id"]


# ---------------------------------------------------------------------------
# Queue / match lifecycle jobs
# ---------------------------------------------------------------------------

async def queue_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "JOINING" or game.get("mode") != "SOLO":
        context.job.schedule_removal()
        return
    await context.bot.send_message(
        chat_id,
        f"⏳ <b>Queue is open!</b> Type /join to enter the match! "
        f"There are 35 seconds left to join. (Total: {len(game['players'])}) 🏏",
        parse_mode="HTML",
    )


async def auto_start_match(context: ContextTypes.DEFAULT_TYPE):
    job     = context.job
    chat_id = job.data["chat_id"]
    for j in context.job_queue.get_jobs_by_name(f"queueremind_{chat_id}"):
        j.schedule_removal()
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") != "JOINING":
        return
    if len(game.get("players", [])) >= 2:
        game.update({
            "state": "PLAYING", "waiting_for": "BOWLER",
            "batter_idx": 0, "bowler_idx": 1,
            "balls_bowled": 0, "special_used_this_over": False, "is_free_hit": False,
        })
        _first_bowler = game["players"][1] if len(game["players"]) > 1 else None
        if _first_bowler:
            _first_bowler["_spell_balls0"] = _first_bowler.get("balls_bowled", 0)
            _first_bowler["_spell_runs0"]  = _first_bowler.get("conceded", 0)
            _first_bowler["_spell_wkts0"]  = _first_bowler.get("wickets", 0)
        await context.bot.send_message(
            chat_id,
            "⏳ <b>70 seconds are up! THE MATCH AUTO-STARTS NOW!</b> 🚨\nLet's head to the pitch! 🏟️",
            parse_mode="HTML",
        )
        await trigger_bowl(context, chat_id)
    else:
        game["state"] = "NOT_PLAYING"
        await context.bot.send_message(
            chat_id,
            "⏳ <b>70 seconds are up, but there are not enough players!</b> Match setup abandoned. 🛑",
            parse_mode="HTML",
        )


async def trigger_team_captains(context, chat_id, game):
    game["state"] = "TEAM_CAPTAINS"
    for team_key in ["team_a", "team_b"]:
        random.shuffle(game[team_key]["players"])
        for idx, p in enumerate(game[team_key]["players"], 1):
            p["num"] = idx
    roster = generate_teams_message(game)
    MAX_CAPTION = 1024
    try:
        if len(roster) <= MAX_CAPTION:
            await context.bot.send_photo(chat_id, photo=TEAMS_ROSTER_IMG, caption=roster, parse_mode="HTML")
        else:
            await context.bot.send_photo(chat_id, photo=TEAMS_ROSTER_IMG)
            await context.bot.send_message(chat_id, roster, parse_mode="HTML")
    except Exception:
        try:
            await context.bot.send_message(chat_id, roster, parse_mode="HTML")
        except Exception:
            pass
    kb = [[
        InlineKeyboardButton("Team A Captain 👑", callback_data="team_cap_a"),
        InlineKeyboardButton("Team B Captain 👑", callback_data="team_cap_b"),
    ]]
    await context.bot.send_message(
        chat_id,
        "Who will lead the teams? Members click your team's button to become the Captain! ⚡",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def team_join_timeout(context: ContextTypes.DEFAULT_TYPE):
    job     = context.job
    chat_id = job.data["chat_id"]
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "TEAM_JOINING":
        return
    if len(game["team_a"]["players"]) < 2 or len(game["team_b"]["players"]) < 2:
        game["is_paused_waiting_players"] = True
        await context.bot.send_message(
            chat_id,
            "⏳ Time's up! But we need at least 2 players in each team! The queue is paused. ⏸️\n"
            "Once both teams have 2 players, the setup will automatically proceed!",
            parse_mode="HTML",
        )
        return
    await trigger_team_captains(context, chat_id, game)


async def spamfree_timeout(context: ContextTypes.DEFAULT_TYPE):
    job     = context.job
    chat_id = job.data["chat_id"]
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "TEAM_SPAMFREE_WAIT":
        return
    game["spamfree"] = False
    game["state"]    = "PLAYING"
    await context.bot.send_message(
        chat_id,
        "⏳ Time is up! ⚠️ <b>SPAM IS ALLOWED.</b>\n\n"
        "Batting Captain/Host, please select your opening pair using:\n"
        "<code>/batting [number]</code> (do it twice).\nClick on /batting to view batters!!",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.message.chat.type
    chat_id   = update.effective_chat.id

    if chat_type != "private":
        current_time = time.time()
        cooldown = context.bot_data.get(f"start_cooldown_{chat_id}", 0)
        if current_time < cooldown:
            rem = int(cooldown - current_time)
            await update.message.reply_text(f"⏳ Start command is under cooldown! Try again after {rem} seconds.")
            return
        context.bot_data[f"start_cooldown_{chat_id}"] = current_time + 5

    if chat_type == "private":
        if context.args:
            try:
                group_id = int(context.args[0])
                if "active_bowlers" not in context.bot_data:
                    context.bot_data["active_bowlers"] = {}
                context.bot_data["active_bowlers"][update.effective_user.id] = group_id

                game = context.bot_data.get(group_id)
                if game and game.get("state") == "PLAYING" and game.get("waiting_for") == "BOWLER":
                    if game.get("mode") == "SOLO":
                        bowler = game["players"][game["bowler_idx"]]
                    else:
                        bowler = game.get("current_bowler")

                    if bowler and update.effective_user.id == bowler["id"]:
                        keyboard = []
                        if not game.get("special_used_this_over") and game.get("mode") != "TEAM":
                            keyboard.append([InlineKeyboardButton("🎯 Try for yorker 🎯", callback_data=f"special_{group_id}")])
                        await update.message.reply_text(
                            "🥎 <b>Your Turn to Bowl!</b>\nType 1-6 or Try for yorker! 🤔👇",
                            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                            parse_mode="HTML",
                        )
                        return
                    else:
                        await update.message.reply_text("It is not your turn to bowl right now! 🚫🏏")
                        return
            except ValueError:
                pass

        welcome_private = (
            "🏏 <b>PLAY LIVE CRICKET INSIDE TELEGRAM</b>\n\n"
            "⚡ Real-time matches\n"
            "🏆 Compete with friends\n"
            "🎯 Become LEGEND 👑\n\n"
            "Ready to dominate?"
        )
        bot_info   = await context.bot.get_me()
        kb_private = [
            [InlineKeyboardButton("ADD IN GROUP TO PLAY ➕", url=f"https://t.me/{bot_info.username}?startgroup=true")],
            [InlineKeyboardButton("STATS 📊", callback_data="dm_stats"), InlineKeyboardButton("RANKINGS 🏆", callback_data="dm_rankings")],
            [InlineKeyboardButton("Support Group 💬", url="https://t.me/elitexplays")],
            [InlineKeyboardButton("Contact Developer 👨‍💻", url="https://t.me/bexqm")],
        ]
        await update.message.reply_photo(
            photo="https://res.cloudinary.com/dxgfxfoog/image/upload/v1777818831/file_00000000677c71fa8d7d9caa8a1b3cc9_k7l0au.png",
            caption=welcome_private,
            reply_markup=InlineKeyboardMarkup(kb_private),
            parse_mode="HTML",
        )
        return

    if await is_banned(update.effective_user.id):
        return

    game = context.bot_data.get(chat_id)
    if game is None:
        game = {"state": "NOT_PLAYING"}
        context.bot_data[chat_id] = game

    if game.get("state") not in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
        await update.message.reply_text("❌ A match is already active in this group! Finish it or ask an admin to /endmatch first.")
        return

    # Track who initiated /start so only that user can pick the game mode
    game["start_initiator_id"] = update.effective_user.id
    # Reset mode-selection lock so a fresh /start always gets a clean lock
    lock_key = f"mode_select_lock_{chat_id}"
    context.bot_data[lock_key] = asyncio.Lock()

    welcome_text = (
        "Welcome to the <b>ELITE CRICKET BOT</b> Arena! 🏆\n"
        "Join our official community at @elitexplays. 🏏\n\n"
        "🔥 <b>May God bless all of you :)</b> 🔥\n\n"
        "Choose your mode: 👇"
    )
    keyboard = [
        [InlineKeyboardButton("🏏 Solo Game",    callback_data="solo_game"),
         InlineKeyboardButton("👥 Team Game",    callback_data="team_game")],
        [InlineKeyboardButton("🏆 Tournaments",  callback_data="tournaments"),
         InlineKeyboardButton("❌ Cancel",        callback_data="cancel")],
    ]
    await update.message.reply_photo(
        photo="https://res.cloudinary.com/dhe9asdww/image/upload/v1779250947/IMG_20260520_095202_248_w6dee3.jpg",
        caption=welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def create_team_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") != "TEAM_SETUP_HOST":
        await update.message.reply_text("❌ No team game setup is active! Click 'Team Game' in /start first.")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ Only the Game Host can create the teams!")
        return

    game["state"]                     = "TEAM_JOINING"
    game["is_paused_waiting_players"] = False
    game["team_a"] = {"players": [], "captain": None, "score": 0, "wickets": 0, "balls_bowled": 0}
    game["team_b"] = {"players": [], "captain": None, "score": 0, "wickets": 0, "balls_bowled": 0}

    kb = [[
        InlineKeyboardButton("Join Team A 🔴", callback_data="join_team_a"),
        InlineKeyboardButton("Join Team B 🔵", callback_data="join_team_b"),
    ]]
    context.job_queue.run_once(team_join_timeout, 10, data={"chat_id": chat_id}, name=f"team_join_{chat_id}")
    await update.message.reply_text(
        "⚔️ <b>TEAM REGISTRATION OPEN!</b> ⚔️\n\n"
        "Players, choose your sides! You have 10 seconds to join. ⏳\n"
        "<b>(Host can type /rejoin to extend 30s or use /add or /remove)</b>",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML",
    )


async def changecap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ No active team match right now!")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ Only the Game Host can change captains!")
        return
    if game.get("state") in ["TEAM_SETUP_HOST", "TEAM_JOINING", "TEAM_CAPTAINS"] and (
        not game.get("team_a", {}).get("captain") or not game.get("team_b", {}).get("captain")
    ):
        await update.message.reply_text("❌ Cannot change captains before both teams have selected their initial captains!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /changecap a OR /changecap b (while replying to a user's message or tagging @username)")
        return
    team_choice = context.args[0].lower()
    if team_choice not in ["a", "b"]:
        await update.message.reply_text("❌ Please specify team 'a' or 'b'. Example: /changecap a")
        return

    team_key = f"team_{team_choice}"
    target_user, target_username = get_user_from_mention(update)
    target_player = None
    if target_user:
        target_player = next((p for p in game[team_key]["players"] if p["id"] == target_user.id), None)
    elif target_username:
        target_player = next((p for p in game[team_key]["players"] if p.get("username") == target_username), None)

    if not target_player:
        await update.message.reply_text(f"❌ User not found in Team {team_choice.upper()}! Make sure to reply to their message or tag them correctly.")
        return
    game[team_key]["captain"] = target_player["id"]
    _invalidate_scoreboard_pfp_cache(chat_id)
    asyncio.create_task(build_scoreboard_base_image(context, chat_id, game))
    await update.message.reply_text(f"✅ Team {team_choice.upper()} captain changed to {target_player['name']}!")


async def rejoin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "TEAM_JOINING":
        return
    if update.effective_user.id != game.get("host_id"):
        return
    for job in context.job_queue.get_jobs_by_name(f"team_join_{chat_id}"):
        job.schedule_removal()
    context.job_queue.run_once(team_join_timeout, 30, data={"chat_id": chat_id}, name=f"team_join_{chat_id}")
    await update.message.reply_text("⏳ <b>Registration Extended!</b> 30 more seconds to join the teams! 👥", parse_mode="HTML")


async def changeover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM" or game.get("state") != "PLAYING":
        await update.message.reply_text("❌ No active team match is currently playing!")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ You ainttt the host bijhhh  !")
        return
    if game.get("innings") != 1:
        await update.message.reply_text("❌ pehle inning wale pagal thhe jo utne overs mein khele?? ")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("👉 Usage: `/changeover [number]` (e.g., `/changeover 5`)", parse_mode="Markdown")
        return

    new_overs  = int(context.args[0])
    played_overs = game["bowling_team_ref"]["balls_bowled"] // 6
    if new_overs <= played_overs:
        await update.message.reply_text(f"❌ The match has already crossed {played_overs} overs! The new target must be greater than {played_overs} overs.")
        return
    game["target_overs"] = new_overs
    await update.message.reply_text(f"✅ <b>Overs updated!</b> The match is now set for <b>{new_overs} overs</b> per side.", parse_mode="HTML")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ No active team match setup found!")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ You ainttt the host bijhh !")
        return
    if not context.args:
        await update.message.reply_text("Usage: /add a @username1 @username2 ... OR /add b @username1 @username2 ...")
        return
    team_choice = context.args[0].lower()
    if team_choice not in ["a", "b"]:
        await update.message.reply_text("❌ Please specify team 'a' or 'b'. Example: /add a @username")
        return

    team_key = f"team_{team_choice}"
    team_name = "TEAM A 🔴" if team_choice == "a" else "TEAM B 🔵"

    # Collect all @usernames from args (skip the first arg which is team choice)
    mentioned_usernames = [
        arg.lstrip("@").lower()
        for arg in context.args[1:]
        if arg.startswith("@")
    ]

    # Also handle reply-to (single user via reply) if no @mentions given
    if not mentioned_usernames:
        target_user, target_username = get_user_from_mention(update)

        if not target_user and target_username and users_col is not None:
            try:
                db_user = await asyncio.wait_for(
                    users_col.find_one({"username": target_username}), timeout=8.0
                )
            except Exception:
                db_user = None
            if db_user:
                class DummyUser:
                    def __init__(self, uid, fname, uname):
                        self.id         = uid
                        self.first_name = fname
                        self.username   = uname
                        self.is_bot     = False
                target_user = DummyUser(db_user["user_id"], db_user["first_name"], db_user["username"])

        if not target_user:
            await update.message.reply_text("❌ Please reply to a user's message or tag @username(s) after the team letter!")
            return
        if target_user.is_bot:
            await update.message.reply_text("❌ Sorry but bot ko kaise add karu main ?")
            return
        if await is_banned(target_user.id):
            await update.message.reply_text(f"❌ {target_user.first_name} is banned and cannot be added to any match!")
            return
        if is_user_playing_anywhere(context, target_user.id):
            await update.message.reply_text("❌ User is already in a game or in a queue in either this or another group.")
            return

        in_a = any(p["id"] == target_user.id for p in game["team_a"]["players"])
        in_b = any(p["id"] == target_user.id for p in game["team_b"]["players"])
        if in_a:
            await update.message.reply_text(f"❌ {target_user.first_name} is already in Team A 🔴!")
            return
        if in_b:
            await update.message.reply_text(f"❌ {target_user.first_name} is already in Team B 🔵!")
            return

        username = target_user.username.lower() if target_user.username else None
        await init_user_db(target_user.id, target_user.first_name, username)
        new_player = {
            "id": target_user.id, "name": target_user.first_name, "username": username,
            "runs": 0, "balls_faced": 0, "wickets": 0, "conceded": 0,
            "balls_bowled": 0, "is_out": False, "match_4s": 0, "match_6s": 0,
        }
        if game.get("state") != "TEAM_JOINING":
            new_player["num"] = get_next_num(game[team_key]["players"])
        game[team_key]["players"].append(new_player)
        await update.message.reply_text(
            f"✅ <b>{target_user.first_name}</b> has been manually added to {team_name} by the Host! 👥",
            parse_mode="HTML",
        )

        if game.get("is_paused_waiting_players"):
            if len(game["team_a"]["players"]) >= 2 and len(game["team_b"]["players"]) >= 2:
                game["is_paused_waiting_players"] = False
                await context.bot.send_message(chat_id, "✅ Minimum player requirement met! Resuming setup... ▶️")
                await trigger_team_captains(context, chat_id, game)
        return

    # --- Multiple @username handling ---
    added_users   = []
    failed_users  = []

    class DummyUser:
        def __init__(self, uid, fname, uname):
            self.id         = uid
            self.first_name = fname
            self.username   = uname
            self.is_bot     = False

    for uname in mentioned_usernames:
        # Try to resolve from DB
        target_user = None
        if users_col is not None:
            try:
                db_user = await asyncio.wait_for(
                    users_col.find_one({"username": uname}), timeout=8.0
                )
            except Exception:
                db_user = None
            if db_user:
                target_user = DummyUser(db_user["user_id"], db_user["first_name"], db_user["username"])

        if not target_user:
            failed_users.append((f"@{uname}", "Not found in DB (user must have played before)"))
            continue
        if target_user.is_bot:
            failed_users.append((f"@{uname}", "Is a bot"))
            continue
        if await is_banned(target_user.id):
            failed_users.append((f"@{uname}", "User is banned"))
            continue
        if is_user_playing_anywhere(context, target_user.id):
            failed_users.append((f"@{uname}", "Already in a game or queue"))
            continue

        in_a = any(p["id"] == target_user.id for p in game["team_a"]["players"])
        in_b = any(p["id"] == target_user.id for p in game["team_b"]["players"])
        if in_a:
            failed_users.append((f"@{uname}", "Already in Team A 🔴"))
            continue
        if in_b:
            failed_users.append((f"@{uname}", "Already in Team B 🔵"))
            continue

        resolved_username = target_user.username.lower() if target_user.username else None
        await init_user_db(target_user.id, target_user.first_name, resolved_username)
        new_player = {
            "id": target_user.id, "name": target_user.first_name, "username": resolved_username,
            "runs": 0, "balls_faced": 0, "wickets": 0, "conceded": 0,
            "balls_bowled": 0, "is_out": False, "match_4s": 0, "match_6s": 0,
        }
        if game.get("state") != "TEAM_JOINING":
            new_player["num"] = get_next_num(game[team_key]["players"])
        game[team_key]["players"].append(new_player)
        added_users.append(target_user.first_name)

    # Build report message
    report_lines = [f"📋 <b>Add Report — {team_name}</b>\n"]
    if added_users:
        report_lines.append(f"✅ <b>Added ({len(added_users)}):</b>")
        for name in added_users:
            report_lines.append(f"  • {name}")
    if failed_users:
        report_lines.append(f"\n❌ <b>Failed ({len(failed_users)}):</b>")
        for tag, reason in failed_users:
            report_lines.append(f"  • {tag} — {reason}")

    await update.message.reply_text("\n".join(report_lines), parse_mode="HTML")

    if game.get("is_paused_waiting_players"):
        if len(game["team_a"]["players"]) >= 2 and len(game["team_b"]["players"]) >= 2:
            game["is_paused_waiting_players"] = False
            await context.bot.send_message(chat_id, "✅ Minimum player requirement met! Resuming setup... ▶️")
            await trigger_team_captains(context, chat_id, game)


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ No active team match setup found!")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ You ainttt the host buddy !")
        return
    target_user, target_username = get_user_from_mention(update)
    if not target_user and not target_username:
        await update.message.reply_text("❌ Please reply to a user's message or tag their @username properly!")
        return

    removed     = False
    target_name = ""
    for team_key in ["team_a", "team_b"]:
        for p in list(game[team_key]["players"]):
            if (target_user and p["id"] == target_user.id) or (target_username and p.get("username") == target_username):
                striker     = game.get("striker") or {}
                non_striker = game.get("non_striker") or {}
                if p["id"] == striker.get("id") or p["id"] == non_striker.get("id"):
                    await update.message.reply_text(
                        f"❌ Cannot remove <b>{p['name']}</b> — they are currently batting on the pitch!",
                        parse_mode="HTML",
                    )
                    return
                target_name = p["name"]
                game[team_key]["players"].remove(p)
                for i, pr in enumerate(game[team_key]["players"], 1):
                    pr["num"] = i
                removed = True
                break

    if removed:
        await update.message.reply_text(f"✅ <b>{target_name}</b> has been successfully removed from their team! Numbers updated. 🚪", parse_mode="HTML")
    else:
        name_str = target_user.first_name if target_user else target_username
        await update.message.reply_text(f"❌ {name_str} is not in any team!")


async def changehost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM" or game.get("state") in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
        await update.message.reply_text("❌ No active team match to change host!")
        return

    user_id  = update.effective_user.id
    is_host  = (user_id == game.get("host_id"))
    in_team_a = any(p["id"] == user_id for p in game.get("team_a", {}).get("players", []))
    in_team_b = any(p["id"] == user_id for p in game.get("team_b", {}).get("players", []))

    if not (is_host or in_team_a or in_team_b):
        await update.message.reply_text("⚠️ Warning: Only the Game Host or active players in Team A/B can use this command!")
        return

    target_user, target_username = get_user_from_mention(update)
    if not target_user and target_username and users_col is not None:
        db_user = await users_col.find_one({"username": target_username})
        if db_user:
            class DummyUser:
                def __init__(self, uid, fname, uname):
                    self.id = uid; self.first_name = fname; self.username = uname; self.is_bot = False
            target_user = DummyUser(db_user["user_id"], db_user["first_name"], db_user["username"])

    if not target_user:
        await update.message.reply_text("❌ Please reply to a user's message or ensure they have played before if using @username!")
        return
    if target_user.is_bot:
        await update.message.reply_text("❌ Woww giving host to a bot , better /endmatch stupid .")
        return

    if is_host:
        game["host_id"] = target_user.id
        _invalidate_scoreboard_pfp_cache(chat_id)
        asyncio.create_task(build_scoreboard_base_image(context, chat_id, game))
        await update.message.reply_text(f"✅ Host privileges successfully transferred to <b>{target_user.first_name}</b>! 👑", parse_mode="HTML")
    else:
        game["host_vote_target"] = target_user.id
        game["host_vote_name"]   = target_user.first_name
        game["host_votes"]       = set()
        kb = [[InlineKeyboardButton("Vote ✅ (0/4)", callback_data="vote_host")]]
        await update.message.reply_text(
            f"🗳️ Vote initiated to change host to <b>{target_user.first_name}</b>!\n4 votes required.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML",
        )


async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return
    chat_id = update.effective_chat.id
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "JOINING":
        await update.message.reply_text("No match is open for joining! Type /start ❌🏏")
        return
    user = update.effective_user
    if await is_banned(user.id):
        return
    if is_user_playing_anywhere(context, user.id):
        await update.message.reply_text("❌ You are already in a game or in a queue in either this or another group.")
        return
    if any(p["id"] == user.id for p in game.get("players", [])):
        await update.message.reply_text(f"⚠️ <b>{user.first_name}</b>, you are ALREADY in the queue! Please wait for the match to start. ⏳🧍‍♂️", parse_mode="HTML")
        return

    username = user.username.lower() if user.username else None
    await init_user_db(user.id, user.first_name, username)
    game["players"].append({
        "id": user.id, "name": user.first_name, "username": username,
        "runs": 0, "conceded": 0, "wickets": 0,
        "balls_bowled": 0, "balls_faced": 0, "match_4s": 0, "match_6s": 0,
    })

    timer_msg = ""
    if len(game["players"]) == 1:
        context.job_queue.run_once(auto_start_match, 70, data={"chat_id": chat_id}, name=f"autostart_{chat_id}")
        context.job_queue.run_repeating(queue_reminder, interval=35, first=35, data={"chat_id": chat_id}, name=f"queueremind_{chat_id}")
        timer_msg = "\n⏳ <i>Auto-start timer initiated: Match begins in 70 seconds!</i>"
    await update.message.reply_text(
        f"✅ <b>{user.first_name}</b> joined! (Total: {len(game['players'])}) 👥{timer_msg}",
        parse_mode="HTML",
    )


async def leavesolo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game:
        return
    if game.get("state") == "PLAYING":
        await update.message.reply_text("❌ The match has already started! You can't leave now.\n")
        return
    if game.get("state") == "JOINING":
        user_id = update.effective_user.id
        if any(p["id"] == user_id for p in game.get("players", [])):
            game["players"] = [p for p in game["players"] if p["id"] != user_id]
            await update.message.reply_text(
                f"👋 <b>{update.effective_user.first_name}</b> has left the queue. (Total: {len(game['players'])}) 👥",
                parse_mode="HTML",
            )
            if len(game["players"]) == 0:
                for prefix in ["autostart_", "queueremind_"]:
                    for job in context.job_queue.get_jobs_by_name(f"{prefix}{chat_id}"):
                        job.schedule_removal()
                await update.message.reply_text("Queue is empty! 🏏 Timer stopped.")
        else:
            await update.message.reply_text("You are not in the queue! ❌")


async def startsolo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.chat.type == "private":
        return
    if not await is_admin(update.effective_chat, update.effective_user.id):
        await update.message.reply_text("❌ Only group admins can start the match manually!")
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") != "JOINING":
        return
    if len(game.get("players", [])) < 2:
        await update.message.reply_text("We need at least 2 players! 👥🏏")
        return
    for prefix in ["autostart_", "queueremind_"]:
        for job in context.job_queue.get_jobs_by_name(f"{prefix}{chat_id}"):
            job.schedule_removal()
    game.update({
        "state": "PLAYING", "waiting_for": "BOWLER",
        "batter_idx": 0, "bowler_idx": 1,
        "balls_bowled": 0, "special_used_this_over": False, "is_free_hit": False,
    })
    _first_bowler = game["players"][1] if len(game["players"]) > 1 else None
    if _first_bowler:
        _first_bowler["_spell_balls0"] = _first_bowler.get("balls_bowled", 0)
        _first_bowler["_spell_runs0"]  = _first_bowler.get("conceded", 0)
        _first_bowler["_spell_wkts0"]  = _first_bowler.get("wickets", 0)
    await update.message.reply_text("🏏<b>THE MATCH HAS BEGUN!</b> ", parse_mode="HTML")
    await trigger_bowl(context, chat_id)


async def endmatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    if not await is_admin(update.effective_chat, update.effective_user.id):
        await update.message.reply_text("❌ Only group admins can end the match!")
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
        await update.message.reply_text("❌ There is no active match to end!")
        return
    keyboard = [
        [InlineKeyboardButton("Yes, End Match ✅", callback_data=f"endmatch_yes_{chat_id}")],
        [InlineKeyboardButton("Cancel ❌",          callback_data=f"endmatch_no_{chat_id}")],
    ]
    await update.message.reply_text(
        "⚠️ <b>Admin Action:</b> Are you sure you want to force-end the current match?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def soloscore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "SOLO" or game.get("state") in ["NOT_PLAYING", None]:
        await update.message.reply_text("❌ No active solo match is currently being played!")
        return
    await trigger_full_scorecard_message(context, chat_id, game)


async def teamscore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM" or game.get("state") in ["NOT_PLAYING", None]:
        await update.message.reply_text("❌ No active team match is currently being played!")
        return
    await trigger_full_scorecard_message(context, chat_id, game)


async def teams_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM" or game.get("state") in ["NOT_PLAYING", "TEAM_SETUP_HOST"]:
        await update.message.reply_text("❌ No active team match right now!")
        return
    roster = generate_teams_message(game)
    MAX_CAPTION = 1024
    if len(roster) <= MAX_CAPTION:
        await update.message.reply_photo(photo=TEAMS_ROSTER_IMG, caption=roster, parse_mode="HTML")
    else:
        await update.message.reply_photo(photo=TEAMS_ROSTER_IMG)
        await update.message.reply_text(roster, parse_mode="HTML")


async def batting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ There is no active team match currently! This command is only for team matches.")
        return
    if game.get("state") != "PLAYING":
        await update.message.reply_text("❌ The match hasn't started yet!")
        return
    if game.get("waiting_for") not in ["TEAM_OPENERS_BAT", "TEAM_BATTER_SELECT"]:
        await update.message.reply_text("❌ Batters are already on the pitch! You cannot change them right now.")
        return

    batting_team = game["batting_team_ref"]
    if not context.args or not context.args[0].isdigit():
        text = "🏏 <b>AVAILABLE BATTERS:</b>\n"
        for p in batting_team.get("players", []):
            if p.get("is_out"):
                status = "❌ (Out)"
            elif p.get("is_striker") or p.get("is_non_striker"):
                status = "🏏 (On Pitch)"
            else:
                status = "✅ (Available)"
            text += f"[{p.get('num', '?')}] {p['name']} - {status}\n"
        text += "\n👉 <i>Usage: /batting [number] to select.</i>"
        await update.message.reply_text(text, parse_mode="HTML")
        return

    if update.effective_user.id not in [batting_team.get("captain"), game.get("host_id")]:
        await update.message.reply_text("❌ Only the Host or Batting Team Captain can select the batter!")
        return

    p_num    = int(context.args[0])
    selected = next((p for p in batting_team.get("players", []) if p.get("num") == p_num), None)

    if not selected:
        await update.message.reply_text(f"❌ Player {p_num} not found in your team!")
        return
    if selected.get("is_out"):
        await update.message.reply_text(f"❌ {selected['name']} is already out! Select a different player.")
        return

    striker    = game.get("striker") or {}
    non_striker = game.get("non_striker") or {}
    if striker.get("id") == selected["id"] or non_striker.get("id") == selected["id"]:
        await update.message.reply_text(f"❌ {selected['name']} is already on the pitch!")
        return

    if game["waiting_for"] == "TEAM_OPENERS_BAT":
        if not game.get("striker"):
            game["striker"]        = selected
            selected["is_striker"] = True
            await update.message.reply_text(f"🏏 <b>{selected['name']}</b> selected as Striker!", parse_mode="HTML")
        elif not game.get("non_striker"):
            game["non_striker"]         = selected
            selected["is_non_striker"]  = True
            openers_gif = "https://media.giphy.com/media/hGJTJqTNaj0XXkLXZr/giphy.gif"
            caption_txt = (
                f"🏏 <b>{selected['name']}</b> selected as Non-Striker!\n\n"
                "Bowling Team Captain/Host, type /bowling to see bowlers or /bowling [num] to select opening bowler."
            )
            await send_media_safely(context, chat_id, openers_gif, caption_txt)
            game["waiting_for"] = "TEAM_BOWLER_SELECT"
    else:
        if not game.get("striker"):
            game["striker"]        = selected
            selected["is_striker"] = True
        elif not game.get("non_striker"):
            game["non_striker"]         = selected
            selected["is_non_striker"]  = True

        await update.message.reply_text(f"🏏 <b>{selected['name']}</b> walks out to the pitch!", parse_mode="HTML")
        if game.get("need_new_bowler"):
            game["need_new_bowler"] = False
            game["waiting_for"]     = "TEAM_BOWLER_SELECT"
            await update.message.reply_text(
                "Bowling Captain/Host, please select the next bowler using <code>/bowling [num]</code>.",
                parse_mode="HTML",
            )
        else:
            game["waiting_for"] = "BOWLER"
            await trigger_bowl(context, chat_id)


async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ There is no active team match currently! This command is only for team matches.")
        return
    if game.get("state") != "PLAYING":
        await update.message.reply_text("❌ The match hasn't started yet!")
        return
    if game.get("waiting_for") in ["TEAM_OPENERS_BAT", "TEAM_BATTER_SELECT"]:
        await update.message.reply_text("❌ Batters not selected yet! Let the batting team select their batter(s) first.")
        return
    if game.get("waiting_for") not in ["TEAM_BOWLER_SELECT", "BOWLER"]:
        await update.message.reply_text("❌ A bowler is already selected and bowling right now!")
        return
    # If waiting_for is BOWLER and a current_bowler exists, allow change only if first ball not yet locked
    if game.get("waiting_for") == "BOWLER" and game.get("current_bowler") is not None:
        cb = game["current_bowler"]
        balls_in_over = cb.get("balls_bowled", 0) - cb.get("_spell_balls0", cb.get("balls_bowled", 0))
        if balls_in_over > 0:
            await update.message.reply_text("❌ Bowler has already bowled their first ball! You can only change the bowler at the start of a new over.")
            return
        # First ball not yet locked — allow captain/host to change bowler
        # Reset spell trackers on old bowler
        for _k in ("_spell_balls0", "_spell_runs0", "_spell_wkts0"):
            cb.pop(_k, None)
    # Treat stuck BOWLER state (no current_bowler) as TEAM_BOWLER_SELECT
    if game.get("waiting_for") == "BOWLER" and game.get("current_bowler") is None:
        game["waiting_for"] = "TEAM_BOWLER_SELECT"

    bowling_team = game["bowling_team_ref"]
    if not context.args or not context.args[0].isdigit():
        text = "🥎 <b>AVAILABLE BOWLERS:</b>\n"
        for p in bowling_team.get("players", []):
            status = "✅ (Available)"
            if game.get("last_bowler_id") == p["id"]:
                status = "⏳ (Bowled Last Over)"
            cb = game.get("current_bowler") or {}
            if cb.get("id") == p["id"]:
                status = "🥎 (Bowling Now)"
            text += f"[{p.get('num', '?')}] {p['name']} - {p.get('balls_bowled', 0)//6}.{p.get('balls_bowled', 0)%6} Ov - {status}\n"
        text += "\n👉 <i>Usage: /bowling [number] to select.</i>"
        await update.message.reply_text(text, parse_mode="HTML")
        return

    if update.effective_user.id not in [bowling_team.get("captain"), game.get("host_id")]:
        await update.message.reply_text("❌ Only the Host or Bowling Team Captain can select the bowler!")
        return

    p_num    = int(context.args[0])
    selected = next((p for p in bowling_team.get("players", []) if p.get("num") == p_num), None)
    if not selected:
        await update.message.reply_text(f"❌ Player {p_num} not found in your team!")
        return
    if game.get("last_bowler_id") == selected["id"]:
        await update.message.reply_text("❌ A bowler cannot bowl two consecutive overs!")
        return

    game["current_bowler"] = selected
    game["waiting_for"]    = "BOWLER"
    selected["_spell_balls0"] = selected.get("balls_bowled", 0)
    selected["_spell_runs0"]  = selected.get("conceded", 0)
    selected["_spell_wkts0"]  = selected.get("wickets", 0)
    await update.message.reply_text(f"🥎 <b>{selected['name']}</b> is handed the ball!", parse_mode="HTML")
    if game.get("innings_start_msg_pending"):
        game["innings_start_msg_pending"] = False
        await update.message.reply_text("🚨 <b>THE INNINGS HAS BEGUN!</b>", parse_mode="HTML")
    await trigger_bowl(context, chat_id)


async def userstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    target_user, target_username = get_user_from_mention(update)
    if not target_user and not target_username:
        target_user = update.effective_user
    if users_col is None:
        await msg.reply_text("❌ Database connection error.")
        return
    try:
        user_data = None
        if target_user:
            user_data = await users_col.find_one({"user_id": target_user.id})
        elif target_username:
            user_data = await users_col.find_one({"username": target_username})
        if not user_data:
            name = target_user.first_name if target_user else target_username
            await msg.reply_text(f"❌ Ek bhi match khela hai tune is bot se jo stats dekh raha? {name}.")
            return

        hs_runs  = user_data.get("highest_score", {}).get("runs", 0)
        hs_balls = user_data.get("highest_score", {}).get("balls", 0)
        total_runs   = user_data.get("total_runs", 0)
        balls_faced  = user_data.get("balls_faced", 0)
        sr           = (total_runs / balls_faced * 100) if balls_faced > 0 else 0
        balls_bowled = user_data.get("balls_bowled", 0)
        runs_conceded = user_data.get("runs_conceded", 0)
        overs        = balls_bowled // 6
        rem_balls    = balls_bowled % 6
        eco          = (runs_conceded / balls_bowled * 6) if balls_bowled > 0 else 0

        exp   = user_data.get("exp", 0)
        level = get_user_level(exp)
        next_level_name, exp_needed = get_next_level_info(exp)
        total_matches = user_data.get("team_matches", 0) + user_data.get("solo_matches", 0)
        outs  = max(1, total_matches - user_data.get("ducks", 0))
        avg   = total_runs / outs if total_runs > 0 else 0

        exp_line = (
            f"⭐ <b>EXP:</b> {exp} | Next: <b>{next_level_name}</b> (Need {exp_needed} more EXP)\n"
            if next_level_name
            else f"⭐ <b>EXP:</b> {exp} | 🏆 <b>MAX LEVEL REACHED!</b>\n"
        )

        stats_text  = f"🚀 <b>{level} STATISTICS</b> \n═══════════════\n"
        stats_text += f"👤 <b>Name:</b> {user_data.get('first_name', 'Unknown')}\n🆔 <b>ID:</b> <code>{user_data.get('user_id', 'Unknown')}</code>\n{exp_line}ㅤㅤ\n"
        stats_text += f"🏏 <b>BATTING STATS</b>\n🌀 <b>Highest Score:</b> {hs_runs} ({hs_balls})\n👀 <b>Total Runs:</b> {total_runs}\n🎀 <b>Batting Avg:</b> {avg:.2f}\n⚡ <b>Strike Rate:</b> {sr:.2f}\n"
        stats_text += f"💥 <b>6s:</b> {user_data.get('total_6s', 0)} | <b>4s:</b> {user_data.get('total_4s', 0)}\n🕸️ <b>100s:</b> {user_data.get('centuries', 0)} | <b>50s:</b> {user_data.get('half_centuries', 0)}\n"
        stats_text += f"🔸 <b>Ducks 🦆:</b> {user_data.get('ducks', 0)}\nㅤ\n"
        stats_text += f"🥎 <b>BOWLING STATS</b>\n👾 <b>Wickets:</b> {user_data.get('wickets', 0)}\n🌪️ <b>Hat-Tricks:</b> {user_data.get('hat_tricks', 0)}\n🧤 <b>Catches:</b> {user_data.get('catches', 0)}\n"
        stats_text += f"🍁 <b>Overs Bowled:</b> {overs}.{rem_balls}\n💐 <b>Economy:</b> {eco:.2f}\nㅤ\n"
        stats_text += f"🏆 <b>MATCH &amp; AWARDS</b>\n⛄ <b>Solo Matches:</b> {user_data.get('solo_matches', 0)}\n☃️ <b>Team Matches:</b> {user_data.get('team_matches', 0)}\n"
        stats_text += f"🎉 <b>MOTM Awards:</b> {user_data.get('motm', 0)}\nㅤ\n #elite_bots"

        # Try to generate the custom userstats card image
        target_uid = target_user.id if target_user else None
        card_bytes = None
        if target_uid and PIL_AVAILABLE:
            card_bytes = await generate_userstats_image(
                context,
                user_id=target_uid,
                total_runs=total_runs,
                hs_runs=hs_runs,
                hs_balls=hs_balls,
                avg=avg,
                ducks=user_data.get("ducks", 0),
                half_centuries=user_data.get("half_centuries", 0),
                centuries=user_data.get("centuries", 0),
                wickets=user_data.get("wickets", 0),
                eco=eco,
                hat_tricks=user_data.get("hat_tricks", 0),
            )

        if card_bytes:
            await msg.reply_photo(
                photo=io.BytesIO(card_bytes),
                caption=stats_text,
                parse_mode="HTML",
            )
        else:
            stats_img = "https://res.cloudinary.com/dxgfxfoog/image/upload/v1777818873/file_00000000fa6871fa8d9b30faff9899ae_hbyn9j.png"
            await msg.reply_photo(photo=stats_img, caption=stats_text, parse_mode="HTML")
    except Exception as e:
        print(f"Error fetching stats: {e}")
        await msg.reply_text("❌ An error occurred while fetching stats.")


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("WEEKLY LEADERBOARD 📅",  callback_data="lb_weekly")],
        [InlineKeyboardButton("LIFETIME LEADERBOARD 🏆", callback_data="lb_lifetime")],
    ]
    await update.message.reply_text(
        "📊 <b>View our top performers!</b>\nSelect a leaderboard below:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML",
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ You ain't the owner of this bot biiichhh.")
        return
    message_to_send = update.message.reply_to_message
    text = None
    if not message_to_send:
        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message> or reply to a message with /broadcast")
            return
        text = update.message.text.split(" ", 1)[1]
    if chats_col is None:
        await update.message.reply_text("Database not connected.")
        return
    success = 0; failed = 0
    status_msg = await update.message.reply_text("Broadcasting started... ⏳")
    async for chat in chats_col.find({}):
        cid = chat["chat_id"]
        try:
            if message_to_send:
                await context.bot.copy_message(chat_id=cid, from_chat_id=message_to_send.chat.id, message_id=message_to_send.message_id)
            else:
                await context.bot.send_message(chat_id=cid, text=text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)
    await status_msg.edit_text(
        f"✅ <b>Broadcast finished!</b>\n\n📨 Sent: {success}\n❌ Failed: {failed}",
        parse_mode="HTML",
    )


async def forward_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /forward — owner-only.
    Reply to a message to forward it to every known chat, preserving the origin header.
    """
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ You ain't the owner of this bot biiichhh.")
        return
    message_to_forward = update.message.reply_to_message
    if not message_to_forward:
        await update.message.reply_text(
            "❌ Reply to a message with <code>/forward</code> to forward it to all chats.",
            parse_mode="HTML",
        )
        return
    if chats_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    success = 0; failed = 0
    status_msg = await update.message.reply_text("📨 Forwarding started... ⏳")
    async for chat in chats_col.find({}):
        cid = chat["chat_id"]
        try:
            await context.bot.forward_message(
                chat_id=cid,
                from_chat_id=message_to_forward.chat.id,
                message_id=message_to_forward.message_id,
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)
    await status_msg.edit_text(
        f"✅ <b>Forward finished!</b>\n\n📨 Sent: {success}\n❌ Failed: {failed}",
        parse_mode="HTML",
    )


async def permit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /permit — owner-only.
    Reply to a user's message (or pass their ID) and optionally a duration:
      /permit          → lifetime
      /permit 10d      → 10 days
      /permit 2h       → 2 hours
    Removes the permit:
      /permit revoke   → revoke permission
    Stores in DB so data survives bot restarts.
    """
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ You ain't the owner of this bot biiichhh.")
        return
    if permitted_hosts_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    # ── Resolve target user ────────────────────────────────────────────
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        # First arg might be a numeric user ID
        first = context.args[0]
        if first.lstrip("-").isdigit():
            # Fake a simple object with id and name
            class _FakeUser:
                id = int(first)
                full_name = str(first)
                username = None
            target_user = _FakeUser()
            context.args = context.args[1:]  # shift args so duration parsing works

    if not target_user:
        await update.message.reply_text(
            "❌ Reply to a user's message (or pass their ID as the first arg) to permit them.\n\n"
            "<b>Usage:</b>\n"
            "  <code>/permit</code>       — lifetime (reply)\n"
            "  <code>/permit 10d</code>   — 10 days\n"
            "  <code>/permit 2h</code>    — 2 hours\n"
            "  <code>/permit revoke</code> — remove permission",
            parse_mode="HTML",
        )
        return

    # ── Revoke? ────────────────────────────────────────────────────────
    if context.args and context.args[0].lower() == "revoke":
        await permitted_hosts_col.delete_one({"user_id": target_user.id})
        await update.message.reply_text(
            f"🚫 Permission <b>revoked</b> for <code>{target_user.id}</code> "
            f"({getattr(target_user, 'full_name', str(target_user.id))}).",
            parse_mode="HTML",
        )
        return

    # ── Parse duration ─────────────────────────────────────────────────
    expires = None          # None = lifetime
    duration_label = "lifetime ♾️"
    if context.args:
        dur_str = context.args[0].lower().strip()
        try:
            if dur_str.endswith("d"):
                seconds = int(dur_str[:-1]) * 86400
                expires = time.time() + seconds
                duration_label = f"{dur_str[:-1]} day(s) 📅"
            elif dur_str.endswith("h"):
                seconds = int(dur_str[:-1]) * 3600
                expires = time.time() + seconds
                duration_label = f"{dur_str[:-1]} hour(s) ⏰"
            elif dur_str.endswith("m"):
                seconds = int(dur_str[:-1]) * 60
                expires = time.time() + seconds
                duration_label = f"{dur_str[:-1]} minute(s) ⏱️"
            else:
                await update.message.reply_text(
                    "❌ Invalid duration format. Use <code>Xd</code>, <code>Xh</code>, or <code>Xm</code>.",
                    parse_mode="HTML",
                )
                return
        except ValueError:
            await update.message.reply_text("❌ Invalid duration number.", parse_mode="HTML")
            return

    # ── Upsert into DB ─────────────────────────────────────────────────
    doc = {
        "user_id":    target_user.id,
        "name":       getattr(target_user, "full_name", str(target_user.id)),
        "username":   getattr(target_user, "username", None),
        "expires":    expires,
        "granted_by": update.effective_user.id,
        "granted_at": time.time(),
    }
    await permitted_hosts_col.update_one(
        {"user_id": target_user.id},
        {"$set": doc},
        upsert=True,
    )

    target_name = getattr(target_user, "full_name", str(target_user.id))
    await update.message.reply_text(
        f"✅ <b>Permission granted!</b>\n\n"
        f"👤 User: <a href='tg://user?id={target_user.id}'>{target_name}</a> "
        f"(<code>{target_user.id}</code>)\n"
        f"⏳ Duration: <b>{duration_label}</b>\n\n"
        f"They can now use <code>/penalty</code> in group matches.",
        parse_mode="HTML",
    )


async def rpermit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /rpermit — owner-only.
    Reply to a user's message (or pass their ID) to remove their permit.
    """
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ You ain't the owner of this bot biiichhh.")
        return
    if permitted_hosts_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    # ── Resolve target user ────────────────────────────────────────────
    target_user = None
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        first = context.args[0]
        if first.lstrip("-").isdigit():
            class _FakeUser:
                id = int(first)
                full_name = str(first)
                username = None
            target_user = _FakeUser()

    if not target_user:
        await update.message.reply_text(
            "❌ Reply to a user's message (or pass their ID as the first arg) to remove their permit.\n\n"
            "<b>Usage:</b>\n"
            "  <code>/rpermit</code>        — reply to the user\n"
            "  <code>/rpermit 123456789</code> — pass user ID",
            parse_mode="HTML",
        )
        return

    result = await permitted_hosts_col.delete_one({"user_id": target_user.id})
    target_name = getattr(target_user, "full_name", str(target_user.id))

    if result.deleted_count:
        await update.message.reply_text(
            f"🚫 Permit <b>removed</b> for <a href='tg://user?id={target_user.id}'>{target_name}</a> "
            f"(<code>{target_user.id}</code>).\n"
            f"They are no longer a permitted host.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"ℹ️ No permit found for <code>{target_user.id}</code> — nothing to remove.",
            parse_mode="HTML",
        )


async def botstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("Jaa jaake chaddhi badal le pehle owner command use karega.")
        return
    if chats_col is None:
        await update.message.reply_text("Database not connected.")
        return

    import datetime
    now = datetime.datetime.utcnow()
    today_start = datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc)
    today_ts = int(today_start.timestamp())

    users_count      = await users_col.count_documents({})
    groups_count     = await chats_col.count_documents({"type": {"$in": ["group", "supergroup"]}})
    loyals_count     = await chats_col.count_documents({"type": "private"})
    users_today      = await users_col.count_documents({"last_seen": {"$gte": today_ts}})
    groups_today     = await chats_col.count_documents({
        "type": {"$in": ["group", "supergroup"]},
        "last_active": {"$gte": today_ts},
    })
    banned_count     = await banned_users_col.count_documents({}) if banned_users_col is not None else 0
    permitted_count  = await permitted_hosts_col.count_documents({}) if permitted_hosts_col is not None else 0
    matches_count    = await match_history_col.count_documents({}) if match_history_col is not None else 0
    active_games     = sum(
        1 for v in context.bot_data.values()
        if isinstance(v, dict) and v.get("state") not in [None, "NOT_PLAYING", "TEAM_FINISHED"]
    )

    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👤 Total Users: <b>{users_count}</b>\n"
        f"👥 Total Groups: <b>{groups_count}</b>\n"
        f"💌 DM Users (Loyals): <b>{loyals_count}</b>\n"
        f"🏏 Total Matches Recorded: <b>{matches_count}</b>\n"
        f"🚫 Banned Users: <b>{banned_count}</b>\n"
        f"🔑 Permitted Hosts: <b>{permitted_count}</b>\n"
        f"⚡ Active Games Right Now: <b>{active_games}</b>\n\n"
        f"📅 <b>Today's Activity</b>\n"
        f"🟢 Users who used bot today: <b>{users_today}</b>\n"
        f"🏘️ Groups active today: <b>{groups_today}</b>",
        parse_mode="HTML",
    )


async def delstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if chats_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    confirm = await update.message.reply_text("⏳ Resetting bot stats...")
    # Delete all chat tracking docs (resets groups, DMs, today activity to 0)
    await chats_col.delete_many({})
    # Delete all match history docs (resets matches count to 0)
    if match_history_col is not None:
        await match_history_col.delete_many({})
    # Reset last_seen on all users so "users today" goes to 0,
    # but leave ALL game-stat fields untouched (exp, runs, wickets, etc.)
    await users_col.update_many({}, {"$unset": {"last_seen": ""}})
    await confirm.edit_text(
        "✅ <b>Bot stats have been reset to 0!</b>\n\n"
        "🗑 Groups &amp; DMs tracking: cleared\n"
        "🗑 Match history records: cleared\n"
        "🔄 User activity (last_seen): reset\n\n"
        "⚠️ <i>User game stats (runs, wickets, exp, etc.) were NOT touched.</i>",
        parse_mode="HTML",
    )


async def botgroups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("Sarpanch ji toh chal base.")
        return
    if chats_col is None:
        await update.message.reply_text("Database not connected.")
        return
    groups_cursor = chats_col.find({"type": {"$ne": "private"}})
    groups = await groups_cursor.to_list(length=1000)
    if not groups:
        await update.message.reply_text("Bot is not in any groups right now.")
        return
    total   = len(groups)
    page_sz = 20
    for page_start in range(0, total, page_sz):
        chunk = groups[page_start:page_start + page_sz]
        page_num   = page_start // page_sz + 1
        page_total = (total + page_sz - 1) // page_sz
        text = (
            f"📊 <b>Bot Groups ({total}) — Page {page_num}/{page_total}:</b>\n\n"
        )
        for i, g in enumerate(chunk, page_start + 1):
            title = g.get("title", "Unknown Group")
            gtype = g.get("type", "")
            text += f"{i}. {title} (<code>{g['chat_id']}</code>) [{gtype}]\n"
        await update.message.reply_text(text, parse_mode="HTML")


async def groupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /info <group_id>\nExample: /info -1001234567890")
        return
    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid group ID. Must be a number.")
        return
    if chats_col is None:
        await update.message.reply_text("Database not connected.")
        return
    doc = await chats_col.find_one({"chat_id": group_id})
    if not doc:
        await update.message.reply_text(
            f"❌ No record found for group ID <code>{group_id}</code>.\n"
            "The bot may not have interacted in that group yet.",
            parse_mode="HTML",
        )
        return
    text = (
        f"📋 <b>Group Info</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏷 <b>Title:</b> {doc.get('title', 'Unknown')}\n"
        f"🆔 <b>ID:</b> <code>{doc.get('chat_id', group_id)}</code>\n"
        f"📂 <b>Type:</b> {doc.get('type', 'Unknown')}\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("Use /history in a group where matches are played!")
        return
    if match_history_col is None:
        await update.message.reply_text("Database not connected.")
        return
    records = await match_history_col.find(
        {"chat_id": chat_id}
    ).sort("timestamp", -1).to_list(length=5)
    if not records:
        await update.message.reply_text("📋 No match history yet! Play a match first.")
        return
    kb = []
    for i, rec in enumerate(records):
        ts       = rec.get("timestamp", 0)
        date_str = time.strftime("%d/%m %H:%M", time.localtime(ts))
        mode     = rec.get("mode", "SOLO")
        kb.append([InlineKeyboardButton(
            f"📋 Match {i + 1} — {mode} ({date_str})",
            callback_data=f"hist_{chat_id}_{i}"
        )])
    context.bot_data[f"hist_cache_{chat_id}"] = records
    await update.message.reply_text(
        "📋 <b>MATCH HISTORY</b>\nSelect a match to view details:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML",
    )


async def penalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /penalty A 2 6
    Owner/permitted-host command: deducts 2 balls and 6 runs from Team A.
    Displays Penalty(-6) beautifully in the batting block of the scorecard.
    """
    chat_id = update.effective_chat.id
    caller_id = update.effective_user.id
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Use /penalty in a group during a TEAM match!")
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM" or game.get("state") not in ["PLAYING", "TEAM_BATTER_SELECT", "TEAM_BOWLER_SELECT"]:
        await update.message.reply_text("❌ No active TEAM match in progress!")
        return
    # Only the CURRENT game host may apply penalties — and they must be owner or permitted
    if caller_id != game.get("host_id"):
        await update.message.reply_text("❌ Only the current Game Host can apply penalties!")
        return
    if caller_id not in OWNER_IDS and not await is_permitted_host(caller_id):
        await update.message.reply_text("❌ You must be an owner or permitted host to apply penalties!")
        return

    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/penalty [Team] [Balls] [Runs]</code>\n\n"
            "<b>Example:</b> <code>/penalty A 2 6</code>\n"
            "→ Deducts 2 balls and 6 runs from Team A.",
            parse_mode="HTML",
        )
        return

    team_letter = args[0].upper()
    if team_letter not in ("A", "B"):
        await update.message.reply_text("❌ Team must be <b>A</b> or <b>B</b>.", parse_mode="HTML")
        return
    try:
        balls_deduct = int(args[1])
        runs_deduct  = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Balls and runs must be whole numbers!", parse_mode="HTML")
        return
    if balls_deduct < 0 or runs_deduct < 0:
        await update.message.reply_text("❌ Values must be positive!", parse_mode="HTML")
        return

    team_key = "team_a" if team_letter == "A" else "team_b"
    opp_key  = "team_b"  if team_letter == "A" else "team_a"
    team     = game.get(team_key, {})
    opp_team = game.get(opp_key, {})

    # ── Deduct runs ──────────────────────────────────────────────────────
    old_score = team.get("score", 0)
    team["score"] = max(0, old_score - runs_deduct)
    actual_runs_deducted = old_score - team["score"]

    # ── Deduct balls from the penalised team's batting innings ───────────
    # The opponent's balls_bowled counter drives this team's over count,
    # so incrementing it effectively removes balls from their remaining quota.
    opp_team["balls_bowled"] = opp_team.get("balls_bowled", 0) + balls_deduct

    # ── Record for scorecard display ─────────────────────────────────────
    if "penalties" not in team:
        team["penalties"] = []
    team["penalties"].append({"runs": -actual_runs_deducted, "balls": balls_deduct})

    await update.message.reply_text(
        f"⛔ <b>PENALTY APPLIED!</b>\n\n"
        f"{'🔴 TEAM A' if team_letter == 'A' else '🔵 TEAM B'}\n"
        f"├ 📉 <b>-{actual_runs_deducted} Runs</b>  "
        f"({old_score} → {team['score']})\n"
        f"└ 🥎 <b>-{balls_deduct} Ball(s)</b> deducted\n\n"
        f"📋 <i>Penalty(-{actual_runs_deducted}) recorded in scorecard.</i>",
        parse_mode="HTML",
    )

    # ── Check innings-end conditions after penalty ────────────────────────
    batting_ref  = game.get("batting_team_ref", {})
    bowling_ref  = game.get("bowling_team_ref", {})
    target_balls = game.get("target_overs", 0) * 6

    # If the penalised team is currently batting, check over limit
    if batting_ref is team:
        balls_used = bowling_ref.get("balls_bowled", 0)
        if balls_used >= target_balls:
            await process_team_innings_end(context, chat_id, game)
            return
        # Check if chase is impossible in innings 2
        if game.get("innings") == 2:
            target = game.get("target", 0)
            if team["score"] >= target:
                await process_team_innings_end(context, chat_id, game)
                return


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🏏 Solo Game Guide",   callback_data="help_solo")],
        [InlineKeyboardButton("👥 Team Game Guide",   callback_data="help_team")],
        [InlineKeyboardButton("🎯 Yorker Rules",      callback_data="help_yorker")],
        [InlineKeyboardButton("⏳ AFK Penalties",     callback_data="help_afk")],
        [InlineKeyboardButton("📊 Commands List",     callback_data="help_commands")],
        [InlineKeyboardButton("⭐ Level System",      callback_data="help_levels")],
    ]
    await update.message.reply_text(
        "🏏 <b>ELITE CRICKET BOT — HELP CENTER</b> 🏆\n\n"
        "Welcome! Select a topic below to learn everything about the bot:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML",
    )


async def spamfree_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") != "TEAM_SPAMFREE_WAIT":
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ Only the Game Host can use the spamfree command!")
        return
    for job in context.job_queue.get_jobs_by_name(f"spamfree_{chat_id}"):
        job.schedule_removal()
    game["spamfree"] = True
    game["state"]    = "PLAYING"
    await update.message.reply_text(
        "🛡️ <b>SPAM-FREE MODE ACTIVATED!</b> Bowlers cannot bowl the same delivery more than twice in a row.\n\n"
        "Batting Captain/Host, please select your opening pair using:\n"
        "<code>/batting [number]</code> (do it twice).",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Bowling trigger
# ---------------------------------------------------------------------------

async def trigger_bowl(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    game = context.bot_data.get(chat_id)
    if not game or game.get("state") != "PLAYING":
        return

    if game.get("mode") == "TEAM":
        bowler    = game.get("current_bowler")
        batter    = game.get("striker")
        over_info = (
            f"{game['bowling_team_ref']['balls_bowled'] // 6}."
            f"{game['bowling_team_ref']['balls_bowled'] % 6} / {game.get('target_overs', '?')}"
        )
    else:
        bowler    = game["players"][game["bowler_idx"]]
        batter    = game["players"][game["batter_idx"]]
        over_info = f"{game['balls_bowled']}/{game['spell']} balls"

    if bowler is None or batter is None:
        return

    if "active_bowlers" not in context.bot_data:
        context.bot_data["active_bowlers"] = {}
    context.bot_data["active_bowlers"][bowler["id"]] = chat_id

    try:
        _bi = await context.bot.get_me()
        _bot_username = _bi.username
    except Exception:
        _bot_username = context.bot.username or "bot"
    url          = f"https://t.me/{_bot_username}"
    free_hit_tag = "🚀 <b>FREE HIT ACTIVE!!</b>\n" if game.get("is_free_hit") else ""

    dm_text  = (
        f"🏏 <b>Match in Progress!</b>\n\n"
        f"🏏 Batter: <b>{batter['name']}</b> ({batter.get('runs', 0)} off {batter.get('balls_faced', 0)})\n"
        f"🥎 Over Status: {over_info}.\n\n"
        "👉 <b>Your Turn to Bowl!</b> Type a number from 1 to 6."
    )
    keyboard = []
    if not game.get("special_used_this_over") and game.get("mode") != "TEAM":
        keyboard.append([InlineKeyboardButton("🎯 Try for yorker 🎯", callback_data=f"special_{chat_id}")])

    dm_sent = False
    try:
        await context.bot.send_message(
            chat_id=bowler["id"], text=dm_text,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode="HTML",
        )
        dm_sent = True
    except Exception:
        pass

    if dm_sent:
        group_text = (
            f"{free_hit_tag}📊 <b>Status:</b>\n"
            f"🏏 <b>Batter:</b> {batter['name']} ({batter.get('runs', 0)} off {batter.get('balls_faced', 0)})\n"
            f"🥎 <b>Bowler:</b> {bowler['name']} (Over: {over_info})\n\n"
            f"👉 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>, check your DM to bowl! 🤫🥎"
        )
        group_kb = [[InlineKeyboardButton("Bowl Delivery 🥎", url=url)]]
    else:
        fallback_url = f"https://t.me/{_bot_username}?start={chat_id}"
        group_text = (
            f"{free_hit_tag}📊 <b>Status:</b>\n"
            f"🏏 <b>Batter:</b> {batter['name']} ({batter.get('runs', 0)} off {batter.get('balls_faced', 0)})\n"
            f"🥎 <b>Bowler:</b> {bowler['name']} (Over: {over_info})\n\n"
            f"⚠️ <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>, I couldn't DM you! "
            "Click below to start me, then bowl! 🤫🥎"
        )
        group_kb = [[InlineKeyboardButton("Start Bot & Bowl 🤖", url=fallback_url)]]

    await send_media_safely(context, chat_id, MEDIA["bowler_turn"], group_text, InlineKeyboardMarkup(group_kb))
    set_afk_timer(context, chat_id, bowler["id"], "BOWLER")

    # ── Log bowler entry to log group ────────────────────────────────────────
    try:
        group_title = "Unknown Group"
        try:
            grp = await context.bot.get_chat(chat_id)
            group_title = grp.title or str(chat_id)
        except Exception:
            pass
        log_text = (
            f"🥎 <b>Bowler Entry</b>\n"
            f"👤 Bowler: <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>\n"
            f"📍 Group: <b>{group_title}</b>"
        )
        await context.bot.send_message(LOG_GROUP_ID, log_text, parse_mode="HTML")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Team innings management
# ---------------------------------------------------------------------------

async def process_team_innings_end(context, chat_id, game):
    if game.get("innings") == 1:
        game["innings"] = 2
        game["target"]  = game["batting_team_ref"]["score"] + 1

        # Swap batting and bowling sides
        temp                    = game["batting_team_ref"]
        game["batting_team_ref"] = game["bowling_team_ref"]
        game["bowling_team_ref"] = temp

        for p in game["team_a"]["players"] + game["team_b"]["players"]:
            p["is_striker"]    = False
            p["is_non_striker"] = False
            p["is_out"]        = False

        game["striker"]               = None
        game["non_striker"]           = None
        game["current_bowler"]        = None
        game["last_bowler_id"]        = None
        game["is_free_hit"]           = False
        game["special_used_this_over"] = False
        game["_over_ball_log"]         = []
        game["_over_4s"]               = 0
        game["_over_6s"]               = 0

        text = (
            f"🛑 <b>INNINGS BREAK! AB CHASE KARO !!</b> 🛑\n\n"
            f"🎯 Target for the Bowling team: <b>{game['target']} runs</b> in {game.get('target_overs', '?')} overs.\n\n"
            "Batting Captain/Host, please select your opening pair using:\n"
            "<code>/batting [number]</code> (do it twice)."
        )
        game["waiting_for"]             = "TEAM_OPENERS_BAT"
        game["innings_start_msg_pending"] = True
        await context.bot.send_message(chat_id, text, parse_mode="HTML")
    else:
        team_a_score = game["team_a"]["score"]
        team_b_score = game["team_b"]["score"]
        winning_team = None
        if team_a_score > team_b_score:
            winning_team = game["team_a"]["players"]
        elif team_b_score > team_a_score:
            winning_team = game["team_b"]["players"]
        if winning_team:
            for wp in winning_team:
                await update_user_db(wp["id"], {"exp": 40})

        try:
            await commit_player_stats(game)
        except Exception as e:
            print(f"Stats Error: {e}")

        await save_match_history_to_db(context, chat_id, game)
        game["state"] = "TEAM_FINISHED"
        await context.bot.send_message(chat_id, "<b>MATCH FINISHED !</b> 🏁\nCheck below for scorecard 👇🏻", parse_mode="HTML")
        await trigger_full_scorecard_message(context, chat_id, game)
        await send_top_performers_message(context, chat_id, game)
        game["state"] = "NOT_PLAYING"


# ---------------------------------------------------------------------------
# Callback query handler
# ---------------------------------------------------------------------------

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if await is_banned(user_id):
        return

    # Navigation/ranking callbacks must never be dedup'd — they share the same
    # message_id (edited in-place) and users legitimately re-click them.
    _NO_DEDUP = {
        "rank_main", "rank_ducks", "rank_sixes", "rank_wickets",
        "rank_runs", "rank_sr", "rank_hattricks",
        "rank_centuries", "rank_fifties", "rank_most_runs_match",
        "rank_catches",
        "lb_weekly", "lb_lifetime", "lb_back", "dm_rankings",
    }

    # ── Per-user-per-message dedup — prevents any user from getting a
    #    double response by spam-clicking the same button on the same message
    if query.data not in _NO_DEDUP and not query.data.startswith("hist_"):
        msg_id = query.message.message_id if query.message else 0
        cb_once_key = f"cbonce_{msg_id}_{user_id}_{query.data}"
        if context.bot_data.get(cb_once_key):
            return
        context.bot_data[cb_once_key] = True

    game    = context.bot_data.get(chat_id)
    if game is None:
        game = {"state": "NOT_PLAYING"}
        context.bot_data[chat_id] = game

    # ── Solo game ─────────────────────────────────────────────────────────
    if query.data == "solo_game":
        # Non-initiators are rejected immediately — no lock needed
        if user_id != game.get("start_initiator_id"):
            try:
                await query.answer("⚠️ Only the person who typed /start can choose the game mode!", show_alert=True)
            except Exception:
                pass
            return
        # Lock prevents the initiator from triggering this twice at the same time
        lock_key = f"mode_select_lock_{chat_id}"
        if lock_key not in context.bot_data:
            context.bot_data[lock_key] = asyncio.Lock()
        mode_lock = context.bot_data[lock_key]
        if mode_lock.locked():
            try:
                await query.answer("⚠️ Already processing your selection!", show_alert=True)
            except Exception:
                pass
            return
        async with mode_lock:
            # Re-check state inside the lock to catch any race
            if game.get("state") not in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
                try:
                    await query.answer("❌ A match is already active or setting up!", show_alert=True)
                except Exception:
                    pass
                return
            keyboard = [
                [InlineKeyboardButton("3 Balls 🥎", callback_data="spell_3")],
                [InlineKeyboardButton("6 Balls 🥎", callback_data="spell_6")],
            ]
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_photo(
                chat_id=chat_id,
                photo="https://res.cloudinary.com/dxgfxfoog/image/upload/v1777720022/file_00000000483072079f73014e1bba1fde_l4thrv.png",
                caption="Select Spell Limit: ⚖️🏏",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif query.data == "team_game":
        # Non-initiators are rejected immediately
        if user_id != game.get("start_initiator_id"):
            try:
                await query.answer("⚠️ Only the person who typed /start can choose the game mode!", show_alert=True)
            except Exception:
                pass
            return
        # Lock prevents the initiator from triggering this twice at the same time
        lock_key = f"mode_select_lock_{chat_id}"
        if lock_key not in context.bot_data:
            context.bot_data[lock_key] = asyncio.Lock()
        mode_lock = context.bot_data[lock_key]
        if mode_lock.locked():
            try:
                await query.answer("⚠️ Already processing your selection!", show_alert=True)
            except Exception:
                pass
            return
        async with mode_lock:
            # Re-check state inside the lock to catch any race
            if game.get("state") not in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
                try:
                    await query.answer("❌ A match is already active or setting up!", show_alert=True)
                except Exception:
                    pass
                return
        text = (
            "👥 <b>TEAM GAME MODE</b> 👥\n\n"
            "Form two teams, appoint captains, toss the coin, and clash in an epic T20-style showdown! 🏆🏏\n\n"
            "Who will take charge?"
        )
        kb = [
            [InlineKeyboardButton("HOST BANUNGA 👿", callback_data="host_banunga")],
            [InlineKeyboardButton("CANCEL ❌",        callback_data="cancel")],
        ]
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_photo(
            chat_id=chat_id,
            photo="https://res.cloudinary.com/dxgfxfoog/image/upload/v1777720311/file_00000000332072078d00837e7d719f5e_ybg18b.png",
            caption=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    elif query.data == "host_banunga":
        if game.get("state") == "TEAM_SETUP_HOST":
            try:
                await query.answer("❌ A host has already been selected for this match!", show_alert=True)
            except Exception:
                pass
            return
        if is_user_playing_anywhere(context, user_id):
            try:
                await query.answer("❌ You are already in a game or in a queue in either this or another group.", show_alert=True)
            except Exception:
                await context.bot.send_message(chat_id, "❌ You are already in a game or in a queue in either this or another group.")
            return
        context.bot_data[chat_id] = {"state": "TEAM_SETUP_HOST", "host_id": user_id, "mode": "TEAM"}
        try:
            await query.edit_message_caption(
                caption=(
                    f"👑 <a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a> is the Game Host!\n\n"
                    "Host, please send /create_team to open the team registration."
                ),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass

    elif query.data == "join_team_a":
        if game.get("state") != "TEAM_JOINING":
            return
        if is_user_playing_anywhere(context, user_id):
            await context.bot.send_message(chat_id, "❌ You are already in a game or in a queue in either this or another group.")
            return

        lock_key = f"team_join_lock_{chat_id}"
        if lock_key not in context.bot_data:
            context.bot_data[lock_key] = asyncio.Lock()
        async with context.bot_data[lock_key]:
            in_a = any(p["id"] == user_id for p in game["team_a"]["players"])
            in_b = any(p["id"] == user_id for p in game["team_b"]["players"])
            if in_a or in_b:
                try:
                    await query.answer(f"⚠️ You are already in {'Team A 🔴' if in_a else 'Team B 🔵'}! Wait for the host to start.", show_alert=True)
                except Exception:
                    pass
                return
            username = update.effective_user.username.lower() if update.effective_user.username else None
            await init_user_db(user_id, update.effective_user.first_name, username)
            game["team_a"]["players"].append({
                "id": user_id, "name": update.effective_user.first_name, "username": username,
                "runs": 0, "balls_faced": 0, "wickets": 0, "conceded": 0,
                "balls_bowled": 0, "is_out": False, "match_4s": 0, "match_6s": 0,
            })

        await context.bot.send_message(chat_id, f"🔴 <b>{update.effective_user.first_name}</b> joined Team A!", parse_mode="HTML")
        if game.get("is_paused_waiting_players") and len(game["team_a"]["players"]) >= 2 and len(game["team_b"]["players"]) >= 2:
            game["is_paused_waiting_players"] = False
            await context.bot.send_message(chat_id, "✅ Minimum player requirement met! Resuming setup... ▶️")
            await trigger_team_captains(context, chat_id, game)

    elif query.data == "join_team_b":
        if game.get("state") != "TEAM_JOINING":
            return
        if is_user_playing_anywhere(context, user_id):
            await context.bot.send_message(chat_id, "❌ You are already in a game or in a queue in either this or another group.")
            return

        lock_key = f"team_join_lock_{chat_id}"
        if lock_key not in context.bot_data:
            context.bot_data[lock_key] = asyncio.Lock()
        async with context.bot_data[lock_key]:
            in_a = any(p["id"] == user_id for p in game["team_a"]["players"])
            in_b = any(p["id"] == user_id for p in game["team_b"]["players"])
            if in_a or in_b:
                try:
                    await query.answer(f"⚠️ You are already in {'Team A 🔴' if in_a else 'Team B 🔵'}! Wait for the host to start.", show_alert=True)
                except Exception:
                    pass
                return
            username = update.effective_user.username.lower() if update.effective_user.username else None
            await init_user_db(user_id, update.effective_user.first_name, username)
            game["team_b"]["players"].append({
                "id": user_id, "name": update.effective_user.first_name, "username": username,
                "runs": 0, "balls_faced": 0, "wickets": 0, "conceded": 0,
                "balls_bowled": 0, "is_out": False, "match_4s": 0, "match_6s": 0,
            })

        await context.bot.send_message(chat_id, f"🔵 <b>{update.effective_user.first_name}</b> joined Team B!", parse_mode="HTML")
        if game.get("is_paused_waiting_players") and len(game["team_a"]["players"]) >= 2 and len(game["team_b"]["players"]) >= 2:
            game["is_paused_waiting_players"] = False
            await context.bot.send_message(chat_id, "✅ Minimum player requirement met! Resuming setup... ▶️")
            await trigger_team_captains(context, chat_id, game)

    elif query.data in ["team_cap_a", "team_cap_b"]:
        if game.get("state") != "TEAM_CAPTAINS":
            return
        team_key = "team_a" if query.data == "team_cap_a" else "team_b"
        if not any(p["id"] == user_id for p in game[team_key]["players"]):
            try:
                await query.answer("You are not in this team!", show_alert=True)
            except Exception:
                pass
            return
        if game[team_key]["captain"]:
            try:
                await query.answer("Captain already selected!", show_alert=True)
            except Exception:
                pass
            return
        game[team_key]["captain"] = user_id
        await context.bot.send_message(
            chat_id,
            f"👑 <b>{update.effective_user.first_name}</b> is now Captain of "
            f"{'Team A 🔴' if team_key == 'team_a' else 'Team B 🔵'}!",
            parse_mode="HTML",
        )
        if game["team_a"]["captain"] and game["team_b"]["captain"]:
            # Both captains chosen — pre-generate and cache the scoreboard base image.
            _invalidate_scoreboard_pfp_cache(chat_id)
            asyncio.create_task(build_scoreboard_base_image(context, chat_id, game))
            game["state"]           = "TEAM_TOSS"
            toss_winner_team        = random.choice(["team_a", "team_b"])
            game["toss_winner_team"] = toss_winner_team
            cap_id   = game[toss_winner_team]["captain"]
            cap_name = next(p["name"] for p in game[toss_winner_team]["players"] if p["id"] == cap_id)
            kb = [[
                InlineKeyboardButton("Heads 🪙", callback_data="toss_heads"),
                InlineKeyboardButton("Tails 🪙", callback_data="toss_tails"),
            ]]
            toss_vid   = "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777819028/VID_20260503195638_lhif0h.mp4"
            caption_msg = f"🪙 <b>TOSS TIME!</b>\n<a href='tg://user?id={cap_id}'>{cap_name}</a>, call the toss!"
            await send_media_safely(context, chat_id, toss_vid, caption_msg, InlineKeyboardMarkup(kb))

    elif query.data in ["toss_heads", "toss_tails"]:
        if game.get("state") != "TEAM_TOSS":
            return
        if user_id != game[game["toss_winner_team"]]["captain"]:
            try:
                await query.answer("Only the designated captain can call the toss!", show_alert=True)
            except Exception:
                pass
            return
        won_toss = random.choice([True, False])
        if won_toss:
            game["state"] = "TEAM_TOSS_DECISION"
            winner_name   = "Team A 🔴" if game["toss_winner_team"] == "team_a" else "Team B 🔵"
            kb = [[
                InlineKeyboardButton("Bat 🏏",  callback_data="toss_bat"),
                InlineKeyboardButton("Bowl 🥎", callback_data="toss_bowl"),
            ]]
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id,
                f"🎉 <b>{winner_name}</b> won the toss! What will you do?",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        else:
            game["state"]            = "TEAM_TOSS_DECISION"
            game["toss_winner_team"] = "team_b" if game["toss_winner_team"] == "team_a" else "team_a"
            cap_id   = game[game["toss_winner_team"]]["captain"]
            cap_name = next(p["name"] for p in game[game["toss_winner_team"]]["players"] if p["id"] == cap_id)
            winner_name = "Team A 🔴" if game["toss_winner_team"] == "team_a" else "Team B 🔵"
            kb = [[
                InlineKeyboardButton("Bat 🏏",  callback_data="toss_bat"),
                InlineKeyboardButton("Bowl 🥎", callback_data="toss_bowl"),
            ]]
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id,
                f"❌ You lost the toss!\n\n🎉 <b>{winner_name}</b> "
                f"(<a href='tg://user?id={cap_id}'>{cap_name}</a>) won the toss. What will they choose?",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )

    elif query.data in ["toss_bat", "toss_bowl"]:
        if game.get("state") != "TEAM_TOSS_DECISION":
            return
        if user_id != game[game["toss_winner_team"]]["captain"]:
            try:
                await query.answer("Only the toss winning captain can decide!", show_alert=True)
            except Exception:
                pass
            return
        if query.data == "toss_bat":
            game["batting_team_ref"] = game[game["toss_winner_team"]]
            game["bowling_team_ref"] = game["team_b" if game["toss_winner_team"] == "team_a" else "team_a"]
            dec_text = "bat 🏏"
        else:
            game["bowling_team_ref"] = game[game["toss_winner_team"]]
            game["batting_team_ref"] = game["team_b" if game["toss_winner_team"] == "team_a" else "team_a"]
            dec_text = "bowl 🥎"

        game["state"] = "TEAM_OVERS"
        host_id   = game["host_id"]
        host_name = "Host"
        try:
            host_name = (await context.bot.get_chat_member(chat_id, host_id)).user.first_name
        except Exception:
            pass
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id, f"✅ The captain chose to {dec_text} first!")
        kb = [
            [InlineKeyboardButton(str(o), callback_data=f"tovers_{o}") for o in [3, 5, 10]],
            [InlineKeyboardButton(str(o), callback_data=f"tovers_{o}") for o in [15, 20, 25]],
        ]
        await context.bot.send_message(
            chat_id,
            f"<a href='tg://user?id={host_id}'>{host_name}</a> (Game Host), "
            "select the number of overs for this match:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML",
        )

    elif query.data.startswith("tovers_"):
        if game.get("state") != "TEAM_OVERS":
            return
        if user_id != game.get("host_id"):
            try:
                await query.answer("Only the host can select overs!", show_alert=True)
            except Exception:
                pass
            return
        overs = int(query.data.split("_")[1])
        game.update({
            "target_overs": overs,
            "state": "TEAM_SPAMFREE_WAIT",
            "innings": 1,
            "waiting_for": "TEAM_OPENERS_BAT",
            "is_free_hit": False,
            "special_used_this_over": False,
            "innings_start_msg_pending": True,
            "spamfree": False,
        })
        try:
            await query.edit_message_text(f"✅ Match set for <b>{overs} Overs</b> per side!", parse_mode="HTML", reply_markup=None)
        except Exception:
            pass

        host_id   = game["host_id"]
        host_name = "Host"
        try:
            member    = await context.bot.get_chat_member(chat_id, host_id)
            host_name = member.user.first_name
        except Exception:
            pass

        context.job_queue.run_once(spamfree_timeout, 15, data={"chat_id": chat_id}, name=f"spamfree_{chat_id}")
        await context.bot.send_message(
            chat_id,
            f"⚠️ <a href='tg://user?id={host_id}'>{host_name}</a>, you can make this game spam-free by clicking on /spamfree\n\n"
            "You have 15 seconds to decide. After 15 seconds if you do not /spamfree then spam is allowed and we proceed to the game!!",
            parse_mode="HTML",
        )

    elif query.data.startswith("spell_"):
        # Message-level one-shot flag — once ANY first click is processed on this
        # spell message, every subsequent click from every user is silently dropped
        spell_done_key = f"spell_done_{msg_id}_{chat_id}"
        if context.bot_data.get(spell_done_key):
            return
        # Only the /start initiator can actually pick the spell length; others silently ignored
        if user_id != game.get("start_initiator_id"):
            return
        # Prevent double-processing with a lock
        lock_key = f"spell_setup_lock_{chat_id}"
        if lock_key not in context.bot_data:
            context.bot_data[lock_key] = asyncio.Lock()
        if context.bot_data[lock_key].locked():
            return
        async with context.bot_data[lock_key]:
            # Re-check both guards inside the lock
            if context.bot_data.get(spell_done_key):
                return
            if context.bot_data.get(chat_id, {}).get("state") in ["JOINING", "PLAYING"]:
                return
            # Mark this message as fully handled — no more clicks processed
            context.bot_data[spell_done_key] = True
            spell_len = int(query.data.split("_")[1])
            context.bot_data[chat_id] = {"state": "JOINING", "mode": "SOLO", "spell": spell_len, "players": [], "start_initiator_id": user_id}
        try:
            await query.edit_message_caption(
                caption=(
                    f"?? <b>Queue Open!</b> (Spell: {spell_len} balls) ⚖️\n"
                    "👉 Type /join\n"
                    "👉 Type /leavesolo to exit queue\n"
                    "👉 Admin can type /startsolo"
                ),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass

    elif query.data == "cancel":
        if game.get("state") == "PLAYING":
            try:
                await query.edit_message_caption(caption="❌ Match is already playing! Use /endmatch to stop it.", reply_markup=None)
            except Exception:
                pass
            return
        canceller_name = update.effective_user.first_name
        canceller_id   = update.effective_user.id
        game["state"] = "NOT_PLAYING"
        for prefix in ["autostart_", "team_join_", "queueremind_"]:
            for job in context.job_queue.get_jobs_by_name(f"{prefix}{chat_id}"):
                job.schedule_removal()
        try:
            await query.edit_message_caption(
                caption=f"Setup cancelled by <a href='tg://user?id={canceller_id}'>{canceller_name}</a>. 🏏❌",
                reply_markup=None,
                parse_mode="HTML",
            )
        except Exception:
            try:
                await query.edit_message_text(
                    f"Setup cancelled by <a href='tg://user?id={canceller_id}'>{canceller_name}</a>. 🏏❌",
                    reply_markup=None,
                    parse_mode="HTML",
                )
            except Exception:
                pass

    elif query.data == "vote_host":
        if "host_votes" not in game:
            return
        if user_id in game["host_votes"]:
            try:
                await query.answer("You already voted!", show_alert=True)
            except Exception:
                pass
            return
        game["host_votes"].add(user_id)
        votes = len(game["host_votes"])
        if votes >= 4:
            game["host_id"] = game["host_vote_target"]
            _invalidate_scoreboard_pfp_cache(chat_id)
            asyncio.create_task(build_scoreboard_base_image(context, chat_id, game))
            try:
                await query.edit_message_text(
                    f"✅ Vote passed! Game Host successfully changed to <b>{game['host_vote_name']}</b>! 👑",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass
        else:
            try:
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"Vote ✅ ({votes}/4)", callback_data="vote_host")]]))
            except Exception:
                pass

    elif query.data.startswith("endmatch_"):
        parts  = query.data.split("_")
        action = parts[1]
        targ_chat_id = int(parts[2])
        if not await is_admin(update.effective_chat, update.effective_user.id):
            await context.bot.send_message(chat_id, "❌ Only admins can click this!")
            return
        if action == "yes":
            game_ref = context.bot_data.get(targ_chat_id)
            if game_ref:
                try:
                    await commit_player_stats(game_ref)
                except Exception as e:
                    print(f"Error in stats: {e}")
                game_ref["state"] = "NOT_PLAYING"
                for prefix in ["autostart_", "team_join_", "queueremind_", "afk1_", "afk10_", "afk30_", "afk60_", "afk90_", "spamfree_"]:
                    try:
                        for job in context.job_queue.get_jobs_by_name(f"{prefix}{targ_chat_id}"):
                            job.schedule_removal()
                    except Exception:
                        pass
            ender_name = update.effective_user.first_name
            ender_id   = update.effective_user.id
            try:
                await query.edit_message_text(
                    f"🛑 <b>Match has been force-ended by</b> <a href='tg://user?id={ender_id}'>{ender_name}</a>.",
                    parse_mode="HTML", reply_markup=None,
                )
            except Exception:
                pass
        elif action == "no":
            try:
                await query.edit_message_text("✅ Force-end cancelled. The match continues!", reply_markup=None)
            except Exception:
                pass

    elif query.data.startswith("special_"):
        group_id = int(query.data.split("_")[1])
        game     = context.bot_data.get(group_id)
        if not game or game.get("state") != "PLAYING" or game.get("waiting_for") != "BOWLER":
            return
        if game.get("mode") == "TEAM":
            try:
                await query.answer("❌ Yorker is not available in Team Mode!", show_alert=True)
            except Exception:
                pass
            return
        if game.get("mode") == "SOLO":
            bowler = game["players"][game["bowler_idx"]]
            batter = game["players"][game["batter_idx"]]
        else:
            bowler = game.get("current_bowler")
            batter = game.get("striker")

        if bowler is None or batter is None:
            return
        if update.effective_user.id != bowler["id"] or game.get("special_used_this_over"):
            return
        if "active_bowlers" in context.bot_data and update.effective_user.id in context.bot_data["active_bowlers"]:
            del context.bot_data["active_bowlers"][update.effective_user.id]

        game["special_used_this_over"] = True
        clear_afk_timer(context, group_id)
        roll = random.randint(1, 100)

        if roll <= 60:
            try:
                await query.edit_message_text(
                    "Oops! Missed yorker and gave a <b>WIDE</b> ball! 1 extra run. You must bowl again.",
                    parse_mode="HTML", reply_markup=None,
                )
            except Exception:
                pass
            batter["runs"] = batter.get("runs", 0) + 1
            bowler["conceded"] = bowler.get("conceded", 0) + 1
            if game.get("mode") == "TEAM":
                game["batting_team_ref"]["score"] += 1
            await context.bot.send_message(group_id, "🚨 <b>WIDE BALL!</b> 1 extra run. Bowler must re-bowl! 🥎", parse_mode="HTML")
            await trigger_bowl(context, group_id)

        elif roll <= 80:
            try:
                await query.edit_message_text(
                    "Oops! Missed yorker and gave a <b>NO BALL!</b>\nKoi na kismat ki baat hai!",
                    parse_mode="HTML", reply_markup=None,
                )
            except Exception:
                pass
            game["current_bowl"] = "NO_BALL"
            game["waiting_for"]  = "BATTER"
            hit_opts = "1-6" if game.get("mode") == "SOLO" else "0-6"
            await send_media_safely(
                context, group_id, MEDIA["batter_turn"],
                f"🚨 Ball delivered!! 🥎💨\n👉 <a href='tg://user?id={batter['id']}'>{batter['name']}</a>, type {hit_opts} to hit! 🏏👇",
            )
            set_afk_timer(context, group_id, batter["id"], "BATTER")

        else:
            msg = "🎯 <b>Yorker padi haii !! 😶‍🌫️</b> Let's see how the batter reacts...\n⚠️ If the batter chooses "
            msg += "0-3, they survive. " if game.get("mode") == "TEAM" else "1-3, they survive. "
            msg += "Otherwise, they are OUT! ☝️"
            try:
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=None)
            except Exception:
                pass
            game["current_bowl"] = "YORKER"
            game["waiting_for"]  = "BATTER"
            hit_opts = "1-6" if game.get("mode") == "SOLO" else "0-6"
            await send_media_safely(
                context, group_id, MEDIA["batter_turn"],
                f"🚨 Ball bowled! 🥎💨\n👇 <a href='tg://user?id={batter['id']}'>{batter['name']}</a>, type {hit_opts} to hit!🏏",
            )
            set_afk_timer(context, group_id, batter["id"], "BATTER")

    elif query.data.startswith("help_"):
        topic   = query.data[5:]
        back_kb = [[InlineKeyboardButton("🔙 Back to Help", callback_data="help_main")]]

        if topic == "main":
            kb = [
                [InlineKeyboardButton("🏏 Solo Game Guide",  callback_data="help_solo")],
                [InlineKeyboardButton("👥 Team Game Guide",  callback_data="help_team")],
                [InlineKeyboardButton("🎯 Yorker Rules",     callback_data="help_yorker")],
                [InlineKeyboardButton("⏳ AFK Penalties",    callback_data="help_afk")],
                [InlineKeyboardButton("📊 Commands List",    callback_data="help_commands")],
                [InlineKeyboardButton("⭐ Level System",     callback_data="help_levels")],
            ]
            try:
                await query.edit_message_text(
                    "🏏 <b>ELITE CRICKET BOT — HELP CENTER</b> 🏆\n\n"
                    "Welcome! Select a topic below to learn everything about the bot:",
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        elif topic == "solo":
            text = (
                "🏏 <b>SOLO GAME — HOW TO PLAY</b>\n\n"
                "1️⃣ Type <code>/start</code> in a group.\n"
                "2️⃣ Select <b>Solo Game 🏏</b> and choose spell (3 or 6 balls per turn).\n"
                "3️⃣ Players type <code>/join</code> to enter the queue.\n"
                "4️⃣ Admin types <code>/startsolo</code> or wait 70 seconds to auto-start.\n\n"
                "🎮 <b>Gameplay:</b>\n"
                "• Bowler receives a DM from the bot — type 1-6 to bowl secretly.\n"
                "• Batter types 1-6 in the group chat to hit.\n"
                "• <b>Same number = OUT! ☝️</b>\n"
                "• <b>Different number = Runs scored! 🏃‍♂️</b>\n\n"
                "🔁 Players rotate batting in queue order.\n"
                "📊 Use <code>/soloscore</code> to check live scorecard.\n"
                "🏆 Highest score earns the most EXP!"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

        elif topic == "team":
            text = (
                "👥 <b>TEAM GAME — FULL GUIDE</b>\n\n"
                "1️⃣ Type <code>/start</code> → Select <b>Team Game 👥</b>.\n"
                "2️⃣ Someone clicks <b>HOST BANUNGA 👿</b> to become Game Host.\n"
                "3️⃣ Host types <code>/create_team</code> — team registration opens.\n"
                "4️⃣ Players click <b>Join Team A 🔴</b> or <b>Join Team B 🔵</b>.\n"
                "   (Min. 2 players per team required!)\n"
                "5️⃣ Each team selects a <b>Captain 👑</b> via button.\n"
                "6️⃣ Toss — winning captain calls Heads/Tails.\n"
                "7️⃣ Host picks number of overs (3 to 25).\n"
                "8️⃣ Host can activate <code>/spamfree</code> mode (15s window).\n\n"
                "🎮 <b>During Match:</b>\n"
                "• Batting Captain → <code>/batting [num]</code> to send batter out.\n"
                "• Bowling Captain → <code>/bowling [num]</code> to select bowler.\n"
                "• Bowler types 1-6 via DM | Batter types 0-6 in group.\n"
                "• Odd runs (1, 3, 5) → Strike rotates automatically! 🔄\n"
                "• End of overs → Innings break → Chasing team bats!\n\n"
                "📊 Use <code>/score</code> and <code>/teams</code> for live info.\n"
                "🏆 Team with more runs at the end wins!"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

        elif topic == "yorker":
            text = (
                "🎯 <b>YORKER RULES</b>\n\n"
                "When it's your turn to bowl, click <b>🎯 Try for yorker</b> in the DM.\n"
                "⚠️ Can only be used <b>once per over</b>!\n\n"
                "🎲 <b>3 Possible Outcomes (random):</b>\n\n"
                "❌ <b>60% chance — WIDE BALL!</b>\n"
                "   Bowler missed. 1 extra run given. Must re-bowl that delivery.\n\n"
                "🚨 <b>20% chance — NO BALL!</b>\n"
                "   Batter hits freely. <b>Next ball is a FREE HIT 🚀</b>\n"
                "   (Batter cannot be out on a free hit!)\n\n"
                "🎯 <b>20% chance — YORKER ACTIVATED!</b>\n"
                "   Batter must pick a number to respond:\n"
                "   • <b>Solo Mode:</b> Type 1, 2, or 3 to survive | 4-6 = <b>OUT ☝️</b>\n"
                "   • <b>Team Mode:</b> Type 0, 1, 2, or 3 to survive | 4-6 = <b>OUT ☝️</b>\n\n"
                "💡 <i>Strategic tip: Use yorker when batter is on a high score!</i>"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

        elif topic == "afk":
            text = (
                "⏳ <b>AFK PENALTIES</b>\n\n"
                "If you don't take your turn in time, here's what happens:\n\n"
                "⚠️ <b>10 seconds</b> — Warning #1: 50 seconds left to play!\n"
                "⚠️ <b>30 seconds</b> — Warning #2: 30 seconds left!\n"
                "❌ <b>60 seconds</b> — TIMEOUT! Penalty applied.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🏏 <b>Solo Mode — AFK Player:</b>\n"
                "   Player is <b>eliminated</b> from the match.\n"
                "   If fewer than 2 players remain → match abandoned.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "👥 <b>Team Mode — AFK Batter:</b>\n"
                "   Batter is given OUT. Team score <b>-5 runs</b>. 📉\n"
                "   Captain/Host must select the next batter.\n\n"
                "👥 <b>Team Mode — AFK Bowler:</b>\n"
                "   Batting team gets <b>+5 free runs</b>. 📈\n"
                "   Captain/Host must select a new bowler.\n\n"
                "💡 <i>Always stay active when it's your turn!</i>"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

        elif topic == "commands":
            text = (
                "📊 <b>USEFUL COMMANDS LIST</b>\n\n"
                "🏏 <b>Solo Game:</b>\n"
                "<code>/start</code> — Start a new match\n"
                "<code>/join</code> — Join the solo queue\n"
                "<code>/leavesolo</code> — Leave the solo queue\n"
                "<code>/startsolo</code> — Force start match (Admin)\n"
                "<code>/soloscore</code> — View solo scorecard\n\n"
                "👥 <b>Team Game:</b>\n"
                "<code>/create_team</code> — Open registration (Host)\n"
                "<code>/batting [num]</code> — Select batter (Captain/Host)\n"
                "<code>/bowling [num]</code> — Select bowler (Captain/Host)\n"
                "<code>/teams</code> — View team rosters\n"
                "<code>/score</code> — View team scorecard\n"
                "<code>/spamfree</code> — Enable spam-free mode (Host)\n\n"
                "⚙️ <b>Management:</b>\n"
                "<code>/add a/b</code> — Add player to team (Host)\n"
                "<code>/remove</code> — Remove player from team (Host)\n"
                "<code>/changehost</code> — Transfer host role\n"
                "<code>/changecap a/b</code> — Change team captain (Host)\n"
                "<code>/changeover [n]</code> — Change total overs (1st innings only)\n"
                "<code>/rejoin</code> — Extend join timer by 30s (Host)\n"
                "<code>/endmatch</code> — Force end match (Admin)\n\n"
                "📈 <b>Stats &amp; Info:</b>\n"
                "<code>/userstats</code> — View your career stats\n"
                "<code>/leaderboard</code> — Weekly &amp; lifetime rankings\n"
                "<code>/help</code> — Open this help menu"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

        elif topic == "levels":
            text = (
                "⭐ <b>LEVEL SYSTEM</b>\n\n"
                "Earn EXP by playing and performing well.\n"
                "Your level is shown in <code>/userstats</code>!\n\n"
                "🔰 <b>Newbie</b> — 0 to 999 EXP\n"
                "   Just getting started. Keep playing!\n\n"
                "⚡ <b>Pro</b> — 1,000 to 5,000 EXP\n"
                "   You're getting serious now!\n\n"
                "🌟 <b>Legendary</b> — 5,001 to 8,000 EXP\n"
                "   An elite performer feared by all!\n\n"
                "👑 <b>Unbeaten</b> — 8,001 to 13,000 EXP\n"
                "   An absolute legend feared by all!\n\n"
                "🔱 <b>God</b> — 13,001+ EXP\n"
                "   The pinnacle. Untouchable. Absolute deity! 🏆\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "💰 <b>How to Earn EXP:</b>\n"
                "🏆 Win a solo match → <b>+60 EXP</b>\n"
                "🏆 Win a team match → <b>+40 EXP</b> per winner\n"
                "💯 Score a century (100+) → <b>+150 EXP</b>\n"
                "🏅 Score a half-century (50-99) → <b>+50 EXP</b>\n"
                "☝️ Take a wicket → <b>+20 EXP</b>\n"
                "🎩 Hat-trick (3 wickets in a row!) → <b>+1000 EXP</b>\n"
                "🌟 Player of the Match award → <b>Bonus EXP!</b>"
            )
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
            except Exception:
                pass

    elif query.data == "tournaments":
        try:
            await query.answer(
                "🏆 Tournaments are under maintenance!\nCheck back soon. 🔧",
                show_alert=True,
            )
        except Exception:
            pass

    elif query.data == "reg_confirm_yes":
        reg_data = context.user_data.get("reg_data")
        if not reg_data:
            try:
                await query.edit_message_text("❌ Registration data lost. Please /register again.")
            except Exception:
                pass
            return
        if tourteams_col is None:
            try:
                await query.edit_message_text("❌ Database not connected.")
            except Exception:
                pass
            return
        team_num = await tourteams_col.count_documents({}) + 1
        reg_data["team_number"] = team_num
        reg_data["registered_by"] = user_id
        await tourteams_col.insert_one(reg_data)
        summary = (
            f"✅ <b>NEW TEAM REGISTERED!</b>\n\n"
            f"🔢 Team No: <b>{team_num}</b>\n"
            f"🏏 Team: <b>{reg_data.get('team_name')}</b>\n"
            f"👑 Captain: {reg_data.get('captain')}\n"
            f"🥈 Vice-Captain: {reg_data.get('vc')}\n"
            f"🌟 Retention 1: {reg_data.get('ret1')}\n"
            f"🌟 Retention 2: {reg_data.get('ret2')}\n"
            f"👤 Registered by: <a href='tg://user?id={user_id}'>{update.effective_user.first_name}</a>"
        )
        for oid in OWNER_IDS:
            try:
                if reg_data.get("logo_file_id"):
                    await context.bot.send_photo(
                        chat_id=oid,
                        photo=reg_data["logo_file_id"],
                        caption=summary,
                        parse_mode="HTML",
                    )
                else:
                    await context.bot.send_message(chat_id=oid, text=summary, parse_mode="HTML")
            except Exception:
                pass
        context.user_data.pop("reg_data", None)
        context.user_data.pop("reg_state", None)
        try:
            await query.edit_message_text(
                f"✅ <b>Registration Submitted!</b>\n\n"
                f"Your team <b>{reg_data.get('team_name')}</b> has been assigned number <b>{team_num}</b>.\n"
                f"Owners will confirm your registration shortly. 🙏",
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif query.data == "reg_confirm_no":
        context.user_data.pop("reg_data", None)
        context.user_data.pop("reg_state", None)
        try:
            await query.edit_message_text("❌ Registration cancelled. You can /register again anytime.")
        except Exception:
            pass

    elif query.data == "dm_stats":
        target_user = update.effective_user
        if users_col is None:
            try:
                await context.bot.send_message(chat_id=user_id, text="❌ Database connection error.")
            except Exception:
                pass
            return
        try:
            user_data = await users_col.find_one({"user_id": target_user.id})
            if not user_data:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Ek bhi match khela hai tune is bot se jo stats dekh raha? {target_user.first_name}.",
                )
                return
            from importlib import import_module as _im
            hs_runs  = user_data.get("highest_score", {}).get("runs", 0)
            hs_balls = user_data.get("highest_score", {}).get("balls", 0)
            total_runs    = user_data.get("total_runs", 0)
            balls_faced   = user_data.get("balls_faced", 0)
            sr            = (total_runs / balls_faced * 100) if balls_faced > 0 else 0
            balls_bowled  = user_data.get("balls_bowled", 0)
            runs_conceded = user_data.get("runs_conceded", 0)
            overs         = balls_bowled // 6
            rem_balls     = balls_bowled % 6
            eco           = (runs_conceded / balls_bowled * 6) if balls_bowled > 0 else 0
            exp           = user_data.get("exp", 0)
            level         = get_user_level(exp)
            next_level_name, exp_needed = get_next_level_info(exp)
            total_matches = user_data.get("team_matches", 0) + user_data.get("solo_matches", 0)
            outs  = max(1, total_matches - user_data.get("ducks", 0))
            avg   = total_runs / outs if total_runs > 0 else 0
            exp_line = (
                f"⭐ <b>EXP:</b> {exp} | Next: <b>{next_level_name}</b> (Need {exp_needed} more EXP)\n"
                if next_level_name
                else f"⭐ <b>EXP:</b> {exp} | 🏆 <b>MAX LEVEL REACHED!</b>\n"
            )
            stats_text  = f"📊 <b>{level} STATISTICS</b> 📊\n════════════════════\n"
            stats_text += f"👤 <b>Name:</b> {user_data.get('first_name','Unknown')}\n🆔 <b>ID:</b> <code>{user_data.get('user_id','Unknown')}</code>\n{exp_line}┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            stats_text += f"🏏 <b>BATTING STATS</b>\n🔸 <b>Highest Score:</b> {hs_runs} ({hs_balls})\n🔸 <b>Total Runs:</b> {total_runs}\n🔸 <b>Batting Avg:</b> {avg:.2f}\n🔸 <b>Strike Rate:</b> {sr:.2f}\n"
            stats_text += f"🔸 <b>6s:</b> {user_data.get('total_6s',0)} | <b>4s:</b> {user_data.get('total_4s',0)}\n🔸 <b>100s:</b> {user_data.get('centuries',0)} | <b>50s:</b> {user_data.get('half_centuries',0)}\n"
            stats_text += f"🔸 <b>Ducks 🦆:</b> {user_data.get('ducks',0)}\n┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            stats_text += f"🥎 <b>BOWLING STATS</b>\n🔹 <b>Wickets:</b> {user_data.get('wickets',0)}\n🔹 <b>Hat-Tricks:</b> {user_data.get('hat_tricks',0)}\n🧤 <b>Catches:</b> {user_data.get('catches', 0)}\n"
            stats_text += f"🔹 <b>Overs Bowled:</b> {overs}.{rem_balls}\n🔹 <b>Economy:</b> {eco:.2f}\n┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            stats_text += f"🏆 <b>MATCH &amp; AWARDS</b>\n🔸 <b>Solo Matches:</b> {user_data.get('solo_matches',0)}\n🔸 <b>Team Matches:</b> {user_data.get('team_matches',0)}\n"
            stats_text += f"🔸 <b>MOTM Awards:</b> {user_data.get('motm',0)}\n════════════════════"

            # Try to generate the custom userstats card image
            card_bytes = None
            if PIL_AVAILABLE:
                card_bytes = await generate_userstats_image(
                    context,
                    user_id=target_user.id,
                    total_runs=total_runs,
                    hs_runs=hs_runs,
                    hs_balls=hs_balls,
                    avg=avg,
                    ducks=user_data.get("ducks", 0),
                    half_centuries=user_data.get("half_centuries", 0),
                    centuries=user_data.get("centuries", 0),
                    wickets=user_data.get("wickets", 0),
                    eco=eco,
                    hat_tricks=user_data.get("hat_tricks", 0),
                )

            if card_bytes:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=io.BytesIO(card_bytes),
                    caption=stats_text,
                    parse_mode="HTML",
                )
            else:
                stats_img = "https://res.cloudinary.com/dxgfxfoog/image/upload/v1777818873/file_00000000fa6871fa8d9b30faff9899ae_hbyn9j.png"
                await context.bot.send_photo(chat_id=user_id, photo=stats_img, caption=stats_text, parse_mode="HTML")
        except Exception as e:
            try:
                await context.bot.send_message(chat_id=user_id, text="❌ An error occurred while fetching stats.")
            except Exception:
                pass

    elif query.data == "play_again":
        # Cannot call start_command directly because update.message is None in a callback context
        play_game = context.bot_data.get(chat_id)
        if play_game is None:
            play_game = {"state": "NOT_PLAYING"}
            context.bot_data[chat_id] = play_game
        if play_game.get("state") not in ["NOT_PLAYING", None, "TEAM_FINISHED"]:
            try:
                await query.answer("❌ A match is already active in this group!", show_alert=True)
            except Exception:
                pass
            return
        play_game["start_initiator_id"] = user_id
        # Reset mode-selection lock so buttons work cleanly after play again
        pa_lock_key = f"mode_select_lock_{chat_id}"
        context.bot_data[pa_lock_key] = asyncio.Lock()
        welcome_text = (
            "Welcome to the <b>ELITE CRICKET BOT</b> Arena! 🏆\n"
            "Join our official community at @eclplays. 🏏\n\n"
            "🔥 <b>A tournament is currently going on! Register via @eclregisbot</b> 🔥\n\n"
            "Choose your mode: 👇"
        )
        keyboard = [
            [InlineKeyboardButton("🏏 Solo Game",    callback_data="solo_game"),
             InlineKeyboardButton("👥 Team Game",    callback_data="team_game")],
            [InlineKeyboardButton("🏆 Tournaments",  callback_data="tournaments"),
             InlineKeyboardButton("❌ Cancel",        callback_data="cancel")],
        ]
        await context.bot.send_photo(
            chat_id=chat_id,
            photo="AgACAgUAAxkBAAMTagPgm7w4w1pNi_QIrBPlrL9EBhYAArAPaxvasCFUb0EE-44IDPsBAAMCAAN3AAM7BA",
            caption=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    elif query.data in ["lb_weekly", "lb_lifetime"]:
        if users_col is None:
            try:
                await query.edit_message_text("❌ Database not connected.")
            except Exception:
                pass
            return
        is_weekly  = query.data == "lb_weekly"
        run_field  = "weekly_runs"    if is_weekly else "total_runs"
        wkt_field  = "weekly_wickets" if is_weekly else "wickets"
        bf_field   = "weekly_balls_faced"  if is_weekly else "balls_faced"
        rc_field   = "weekly_conceded"     if is_weekly else "runs_conceded"
        bb_field   = "weekly_balls_bowled" if is_weekly else "balls_bowled"

        pipeline_bat = [
            {"$match": {run_field: {"$gt": 0}}},
            {"$addFields": {"sr": {"$cond": [
                {"$gt": [f"${bf_field}", 0]},
                {"$multiply": [{"$divide": [f"${run_field}", f"${bf_field}"]}, 100]},
                0,
            ]}}},
            {"$sort": {run_field: -1, "sr": -1}},
            {"$limit": 5},
        ]
        top_batters = await users_col.aggregate(pipeline_bat).to_list(5)

        pipeline_bowl = [
            {"$match": {wkt_field: {"$gt": 0}}},
            {"$addFields": {"eco": {"$cond": [
                {"$gt": [f"${bb_field}", 0]},
                {"$multiply": [{"$divide": [f"${rc_field}", f"${bb_field}"]}, 6]},
                999,
            ]}}},
            {"$sort": {wkt_field: -1, "eco": 1}},
            {"$limit": 5},
        ]
        top_bowlers = await users_col.aggregate(pipeline_bowl).to_list(5)

        if is_weekly and not top_batters and not top_bowlers:
            try:
                await query.edit_message_text("⏳ <b>Still fetching data...</b> Play some matches to get on the board!", parse_mode="HTML")
            except Exception:
                pass
            return

        text  = f"🏆 <b>{'WEEKLY' if is_weekly else 'LIFETIME'} LEADERBOARD</b> 🏆\n\n"
        text += "🏏 <b>TOP 5 BATTERS</b>\n"
        for i, b in enumerate(top_batters, 1):
            lvl   = get_user_level(b.get("exp", 0))
            text += f"{i}. {b.get('first_name', 'Unknown')} [{lvl}] - <b>{b.get(run_field, 0)} Runs</b> (SR: {b.get('sr', 0):.1f})\n"

        text += "\n🥎 <b>TOP 5 BOWLERS</b>\n"
        for i, b in enumerate(top_bowlers, 1):
            lvl   = get_user_level(b.get("exp", 0))
            text += f"{i}. {b.get('first_name', 'Unknown')} [{lvl}] - <b>{b.get(wkt_field, 0)} Wkts</b> (Eco: {b.get('eco', 0):.2f})\n"

        kb = [[InlineKeyboardButton("Back 🔙", callback_data="lb_back")]]
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        except Exception:
            pass

    elif query.data == "lb_back":
        kb = [
            [InlineKeyboardButton("WEEKLY LEADERBOARD 📅",  callback_data="lb_weekly")],
            [InlineKeyboardButton("LIFETIME LEADERBOARD 🏆", callback_data="lb_lifetime")],
        ]
        try:
            await query.edit_message_text(
                "📊 <b>View our top performers!</b>\nSelect a leaderboard below:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif query.data == "rank_main":
        kb = [
            [
                InlineKeyboardButton("🦆 Duck Ranking",       callback_data="rank_ducks"),
                InlineKeyboardButton("💥 Sixes Ranking",      callback_data="rank_sixes"),
            ],
            [
                InlineKeyboardButton("🥎 Wickets Ranking",    callback_data="rank_wickets"),
                InlineKeyboardButton("🏃 Total Runs",         callback_data="rank_runs"),
            ],
            [
                InlineKeyboardButton("⚡ Strike Rate",        callback_data="rank_sr"),
                InlineKeyboardButton("🎩 Hat-tricks",         callback_data="rank_hattricks"),
            ],
            [
                InlineKeyboardButton("💯 Centuries",          callback_data="rank_centuries"),
                InlineKeyboardButton("🌟 Half-Centuries",     callback_data="rank_fifties"),
            ],
            [
                InlineKeyboardButton("🏆 Most Runs in Match", callback_data="rank_most_runs_match"),
            ],
            [
                InlineKeyboardButton("🧤 Most Catches",       callback_data="rank_catches"),
            ],
        ]
        try:
            await query.edit_message_text(
                "🏆 <b>WELCOME TO THE HALL OF FAME!</b> 🏆\n\n"
                "This is where legends are remembered.\n"
                "The greatest performers in our arena live here forever.\n\n"
                "🌟 Select a category to see the Top 10:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif query.data == "rank_ducks":
        await _send_ranking(query, "🦆 DUCK RANKING — TOP 10", "ducks", "ducks")

    elif query.data == "rank_sixes":
        await _send_ranking(query, "💥 SIXES RANKING — TOP 10", "total_6s", "sixes")

    elif query.data == "rank_wickets":
        await _send_ranking(query, "🥎 WICKETS RANKING — TOP 10", "wickets", "wickets")

    elif query.data == "rank_runs":
        await _send_ranking(query, "🏃 MOST RUNS — TOP 10", "total_runs", "runs")

    elif query.data == "rank_sr":
        await _send_sr_ranking(query)

    elif query.data == "rank_hattricks":
        await _send_ranking(query, "🎩 HAT-TRICK RANKING — TOP 10", "hat_tricks", "hat-tricks")

    elif query.data == "rank_centuries":
        await _send_ranking(query, "💯 CENTURIES RANKING — TOP 10", "centuries", "centuries")

    elif query.data == "rank_fifties":
        await _send_ranking(query, "🌟 HALF-CENTURIES RANKING — TOP 10", "half_centuries", "half-centuries")

    elif query.data == "rank_most_runs_match":
        await _send_most_runs_in_match_ranking(query)

    elif query.data == "rank_catches":
        await _send_ranking(query, "🧤 MOST CATCHES — TOP 10", "catches", "catches")

    elif query.data.startswith("hist_") and not query.data.startswith("hist_back_"):
        parts = query.data.split("_")
        try:
            hist_chat_id = int(parts[1])
            hist_idx     = int(parts[2])
        except (IndexError, ValueError):
            return
        records = context.bot_data.get(f"hist_cache_{hist_chat_id}")
        if not records and match_history_col is not None:
            records = await match_history_col.find(
                {"chat_id": hist_chat_id}
            ).sort("timestamp", -1).to_list(length=5)
            context.bot_data[f"hist_cache_{hist_chat_id}"] = records
        if not records or hist_idx >= len(records):
            await query.answer("Match not found!", show_alert=True)
            return
        rec      = records[hist_idx]
        ts       = rec.get("timestamp", 0)
        date_str = time.strftime("%d %b %Y, %H:%M", time.localtime(ts))
        mode     = rec.get("mode", "SOLO")
        overs    = rec.get("overs", "?")

        # ── Build full final scorecard ──────────────────────────────────
        text = (
            f"🏆 <b>FINAL SCORECARD</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📅 {date_str}\n"
            f"🏏 {mode} • {overs} overs\n"
            f"━━━━━━━━━━━━━━━━\n\n"
        )

        if mode == "SOLO":
            winner_name = rec.get("winner_name", "?")
            winner_runs = rec.get("winner_runs", 0)
            text += (
                f"🥇 <b>Winner: {winner_name}</b> ({winner_runs} runs)\n\n"
                f"🏏 <b>SCORECARD</b>\n"
                f"─────────────────\n"
            )
            for p in rec.get("players", []):
                ov_str = f"{p.get('balls_bowled',0)//6}.{p.get('balls_bowled',0)%6}"
                sr     = (p.get('runs',0) / p.get('balls_faced',1) * 100) if p.get('balls_faced',0) > 0 else 0
                out_tag = "❌" if p.get("is_out") else "🟢"
                text += (
                    f"{out_tag} <b>{p['name']}</b>\n"
                    f"  🏏 {p.get('runs',0)}({p.get('balls_faced',0)}) SR {sr:.1f}\n"
                    f"  4️⃣ {p.get('match_4s',0)}  6️⃣ {p.get('match_6s',0)}\n"
                    f"  🥎 {p.get('wickets',0)}W • {ov_str} ov\n"
                    f"─────────────────\n"
                )
        else:
            team_a     = rec.get("team_a", {})
            team_b     = rec.get("team_b", {})
            winner_key = rec.get("winner_team", "tie")
            target     = rec.get("target", 0)
            host_name  = rec.get("host_name", "?")
            if winner_key == "team_a":
                w_label = "🔴 TEAM A WINS!"
            elif winner_key == "team_b":
                w_label = "🔵 TEAM B WINS!"
            else:
                w_label = "🤝 MATCH TIED!"
            text += (
                f"🏆 <b>{w_label}</b>\n"
                f"🎯 Target: <b>{target}</b>\n"
                f"🎙️ Host: {host_name}\n\n"
            )
            # Build per-team scorecard block
            for t_key, t_data, t_emoji, t_label in [
                ("team_a", team_a, "🔴", "TEAM A"),
                ("team_b", team_b, "🔵", "TEAM B"),
            ]:
                text += (
                    f"{t_emoji} <b>{t_label}  •  "
                    f"{t_data.get('score',0)}/{t_data.get('wickets',0)}</b>\n"
                    f"👑 Cap: {t_data.get('captain','?')}\n"
                    f"─────────────────\n"
                    f"🏏 <b>BATTING</b>\n"
                )
                bat_shown = False
                for p in t_data.get("players", []):
                    if p.get("balls_faced", 0) == 0 and not p.get("is_out") and p.get("runs", 0) == 0:
                        continue
                    bat_shown = True
                    sr = (p.get("runs", 0) / p.get("balls_faced", 1) * 100) if p.get("balls_faced", 0) > 0 else 0
                    nm = p["name"][:13] + "…" if len(p["name"]) > 13 else p["name"]
                    out_tag = "❌" if p.get("is_out") else "🟢"
                    text += (
                        f"{out_tag} <b>{nm}</b>\n"
                        f"  {p.get('runs',0)}({p.get('balls_faced',0)}) SR {sr:.0f}\n"
                        f"  4️⃣ {p.get('match_4s',0)}  6️⃣ {p.get('match_6s',0)}\n"
                    )
                if not bat_shown:
                    text += "  No batting data\n"
                text += (
                    f"─────────────────\n"
                    f"🥎 <b>BOWLING</b>\n"
                )
                bowl_shown = False
                for p in t_data.get("players", []):
                    if p.get("balls_bowled", 0) <= 0:
                        continue
                    bowl_shown = True
                    ov, bl = divmod(p.get("balls_bowled", 0), 6)
                    eco = (p.get("conceded", 0) / p["balls_bowled"] * 6) if p.get("balls_bowled", 0) > 0 else 0
                    nm  = p["name"][:13] + "…" if len(p["name"]) > 13 else p["name"]
                    text += (
                        f"• <b>{nm}</b>\n"
                        f"  {p.get('wickets',0)}W/{p.get('conceded',0)}R  {ov}.{bl}ov  Eco {eco:.1f}\n"
                    )
                if not bowl_shown:
                    text += "  No bowling data\n"
                text += "\n"

            # Man of the Match
            motm_name    = rec.get("motm_name")
            motm_runs    = rec.get("motm_runs", 0)
            motm_wickets = rec.get("motm_wickets", 0)
            if motm_name:
                text += (
                    f"━━━━━━━━━━━━━━━━\n"
                    f"🏅 <b>MAN OF THE MATCH</b>\n"
                    f"⭐ <b>{motm_name}</b>\n"
                    f"🏏 {motm_runs} runs  🥎 {motm_wickets} wkts\n"
                    f"🎉 Congrats on an amazing game!\n"
                )

        back_kb = [[InlineKeyboardButton("◀️ Back to History", callback_data=f"hist_back_{hist_chat_id}")]]
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_kb), parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id, text, parse_mode="HTML")

    elif query.data.startswith("hist_back_"):
        try:
            hist_chat_id = int(query.data.split("_")[2])
        except (IndexError, ValueError):
            return
        records = context.bot_data.get(f"hist_cache_{hist_chat_id}")
        if not records and match_history_col is not None:
            records = await match_history_col.find(
                {"chat_id": hist_chat_id}
            ).sort("timestamp", -1).to_list(length=5)
            context.bot_data[f"hist_cache_{hist_chat_id}"] = records
        if not records:
            await query.answer("No history found!", show_alert=True)
            return
        kb = []
        for i, rec in enumerate(records):
            ts       = rec.get("timestamp", 0)
            date_str = time.strftime("%d/%m %H:%M", time.localtime(ts))
            mode     = rec.get("mode", "SOLO")
            kb.append([InlineKeyboardButton(
                f"📋 Match {i + 1} — {mode} ({date_str})",
                callback_data=f"hist_{hist_chat_id}_{i}"
            )])
        try:
            await query.edit_message_text(
                "📋 <b>MATCH HISTORY</b>\nSelect a match to view details:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif query.data == "dm_rankings":
        kb = [
            [
                InlineKeyboardButton("🦆 Duck Ranking",       callback_data="rank_ducks"),
                InlineKeyboardButton("💥 Sixes Ranking",      callback_data="rank_sixes"),
            ],
            [
                InlineKeyboardButton("🥎 Wickets Ranking",    callback_data="rank_wickets"),
                InlineKeyboardButton("🏃 Total Runs",         callback_data="rank_runs"),
            ],
            [
                InlineKeyboardButton("⚡ Strike Rate",        callback_data="rank_sr"),
                InlineKeyboardButton("🎩 Hat-tricks",         callback_data="rank_hattricks"),
            ],
            [
                InlineKeyboardButton("💯 Centuries",          callback_data="rank_centuries"),
                InlineKeyboardButton("🌟 Half-Centuries",     callback_data="rank_fifties"),
            ],
            [
                InlineKeyboardButton("🏆 Most Runs in Match", callback_data="rank_most_runs_match"),
            ],
            [
                InlineKeyboardButton("🧤 Most Catches",       callback_data="rank_catches"),
            ],
        ]
        try:
            await query.message.reply_text(
                "🏆 <b>WELCOME TO THE HALL OF FAME!</b> 🏆\n\n"
                "This is where legends are remembered.\n"
                "The greatest performers in our arena live here forever.\n\n"
                "🌟 Select a category to see the Top 10:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text input handler (bowl via DM / bat in group)
# ---------------------------------------------------------------------------

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip() if update.message and update.message.text else ""
    chat_type  = update.message.chat.type if update.message else "private"

    # ── Ban check — blocked users cannot participate ───────────────────────
    if update.effective_user and await is_banned(update.effective_user.id):
        return

    # ── Private DM — Registration flow ────────────────────────────────────
    if chat_type == "private":
        reg_state = context.user_data.get("reg_state")
        if reg_state and reg_state not in ("confirm",):
            reg_data = context.user_data.setdefault("reg_data", {})
            text = user_input

            if reg_state == "team_name":
                if not text:
                    await update.message.reply_text("❌ Team name cannot be empty. Please send your team name:")
                    return
                reg_data["team_name"] = text
                context.user_data["reg_state"] = "logo"
                await update.message.reply_text(
                    f"✅ Team Name: <b>{text}</b>\n\nStep 2️⃣\n"
                    "🖼️ Now send your <b>Team Logo</b> (send as a photo):",
                    parse_mode="HTML",
                )
                return

            elif reg_state == "logo":
                await update.message.reply_text("📸 Please <b>send a photo</b> as your team logo, not text!", parse_mode="HTML")
                return

            elif reg_state == "captain":
                if not text:
                    await update.message.reply_text("❌ Captain cannot be empty. Send captain @username or name:")
                    return
                # Check if this player is already in another team
                if tourteams_col is not None:
                    existing = await tourteams_col.find_one({
                        "$or": [{"captain": text}, {"vc": text}, {"ret1": text}, {"ret2": text}]
                    })
                    if existing:
                        await update.message.reply_text(
                            f"⚠️ <b>{text}</b> is already registered in another team! Please choose a different player.",
                            parse_mode="HTML",
                        )
                        return
                reg_data["captain"] = text
                context.user_data["reg_state"] = "vc"
                await update.message.reply_text(
                    f"✅ Captain: <b>{text}</b>\n\nStep 5️⃣\n"
                    "🥈 Send the <b>Vice-Captain's @username</b>.\n(If no username, send their full name)",
                    parse_mode="HTML",
                )
                return

            elif reg_state == "vc":
                if not text:
                    await update.message.reply_text("❌ Vice-Captain cannot be empty. Send VC @username or name:")
                    return
                if tourteams_col is not None:
                    existing = await tourteams_col.find_one({
                        "$or": [{"captain": text}, {"vc": text}, {"ret1": text}, {"ret2": text}]
                    })
                    if existing:
                        await update.message.reply_text(
                            f"⚠️ <b>{text}</b> is already registered in another team!",
                            parse_mode="HTML",
                        )
                        return
                if text == reg_data.get("captain"):
                    await update.message.reply_text("⚠️ VC cannot be the same as Captain!")
                    return
                reg_data["vc"] = text
                context.user_data["reg_state"] = "ret1"
                await update.message.reply_text(
                    f"✅ Vice-Captain: <b>{text}</b>\n\nStep 6️⃣\n"
                    "🌟 Send <b>Retention 1</b> @username.\n(If no username, send their full name)",
                    parse_mode="HTML",
                )
                return

            elif reg_state == "ret1":
                if not text:
                    await update.message.reply_text("❌ Retention 1 cannot be empty. Send @username or name:")
                    return
                if tourteams_col is not None:
                    existing = await tourteams_col.find_one({
                        "$or": [{"captain": text}, {"vc": text}, {"ret1": text}, {"ret2": text}]
                    })
                    if existing:
                        await update.message.reply_text(
                            f"⚠️ <b>{text}</b> is already registered in another team!",
                            parse_mode="HTML",
                        )
                        return
                already = [reg_data.get("captain"), reg_data.get("vc")]
                if text in already:
                    await update.message.reply_text("⚠️ Retention 1 cannot be the same as Captain or VC!")
                    return
                reg_data["ret1"] = text
                context.user_data["reg_state"] = "ret2"
                await update.message.reply_text(
                    f"✅ Retention 1: <b>{text}</b>\n\nStep 7️⃣\n"
                    "🌟 Send <b>Retention 2</b> @username.\n(If no username, send their full name)",
                    parse_mode="HTML",
                )
                return

            elif reg_state == "ret2":
                if not text:
                    await update.message.reply_text("❌ Retention 2 cannot be empty. Send @username or name:")
                    return
                if tourteams_col is not None:
                    existing = await tourteams_col.find_one({
                        "$or": [{"captain": text}, {"vc": text}, {"ret1": text}, {"ret2": text}]
                    })
                    if existing:
                        await update.message.reply_text(
                            f"⚠️ <b>{text}</b> is already registered in another team!",
                            parse_mode="HTML",
                        )
                        return
                already = [reg_data.get("captain"), reg_data.get("vc"), reg_data.get("ret1")]
                if text in already:
                    await update.message.reply_text("⚠️ Retention 2 cannot be the same as Captain, VC, or Retention 1!")
                    return
                reg_data["ret2"] = text
                context.user_data["reg_state"] = "confirm"
                summary = (
                    f"📋 <b>CONFIRM YOUR REGISTRATION</b>\n\n"
                    f"🏏 <b>Team Name:</b> {reg_data.get('team_name')}\n"
                    f"👑 <b>Captain:</b> {reg_data.get('captain')}\n"
                    f"🥈 <b>Vice-Captain:</b> {reg_data.get('vc')}\n"
                    f"🌟 <b>Retention 1:</b> {reg_data.get('ret1')}\n"
                    f"🌟 <b>Retention 2:</b> {reg_data.get('ret2')}\n\n"
                    f"{'🖼️ Logo: Uploaded ✅' if reg_data.get('logo_file_id') else '🖼️ Logo: Not provided'}\n\n"
                    f"Everything correct? Tap <b>Confirm</b> to submit!"
                )
                kb = [
                    [InlineKeyboardButton("✅ Confirm", callback_data="reg_confirm_yes"),
                     InlineKeyboardButton("❌ Cancel",  callback_data="reg_confirm_no")],
                ]
                if reg_data.get("logo_file_id"):
                    await update.message.reply_photo(
                        photo=reg_data["logo_file_id"],
                        caption=summary,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="HTML",
                    )
                else:
                    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
                return

    if not user_input or not user_input.lstrip("-").isdigit():
        return
    if not user_input.isdigit():
        return
    val       = int(user_input)

    # ── Private DM — BOWLER input ─────────────────────────────────────────
    if chat_type == "private":
        user_id  = update.effective_user.id
        group_id = context.bot_data.get("active_bowlers", {}).get(user_id)
        if not group_id:
            return
        game = context.bot_data.get(group_id)
        if not game or game.get("state") != "PLAYING":
            return
        # Accept bowler input if waiting for bowl OR if stuck at PROCESSING_BATTER (Bug 3 fix)
        if game.get("waiting_for") not in ("BOWLER", "PROCESSING_BATTER"):
            return

        if game.get("mode") == "SOLO":
            bowler = game["players"][game["bowler_idx"]]
            batter = game["players"][game["batter_idx"]]
        else:
            bowler = game.get("current_bowler")
            batter = game.get("striker")

        if bowler is None or batter is None:
            return
        if user_id != bowler["id"]:
            return
        if val < 1 or val > 6:
            await update.message.reply_text("❌ Bowlers can only bowl numbers from 1 to 6!")
            return

        # Spam-free check
        if game.get("mode") == "TEAM" and game.get("spamfree"):
            last_balls = bowler.get("last_balls", [])
            if len(last_balls) >= 2 and last_balls[-1] == val and last_balls[-2] == val:
                await update.message.reply_text(
                    "⚠️ <b>SPAM FREE MODE ACTIVE:</b> You cannot bowl the same delivery more than 2 times in a row! "
                    "Choose a different delivery.",
                    parse_mode="HTML",
                )
                return
            bowler["last_balls"] = (last_balls + [val])[-2:]

        clear_afk_timer(context, group_id)
        game["current_bowl"] = val
        game["waiting_for"]  = "BATTER"
        if user_id in context.bot_data.get("active_bowlers", {}):
            del context.bot_data["active_bowlers"][user_id]

        # Send "Choice locked!" instantly — no URL lookup before this
        hit_opts = "1-6" if game.get("mode") == "SOLO" else "0-6"
        locked_msg = await update.message.reply_text(
            f"Choice locked! 🍁 You bowled a <b>{val}</b>.",
            parse_mode="HTML",
        )

        # Now fetch chat URL and edit the locked message to add back-to-game button
        chat_url = None
        group_title = "Unknown Group"
        try:
            grp = await context.bot.get_chat(group_id)
            group_title = grp.title or str(group_id)
            if grp.username:
                chat_url = f"https://t.me/{grp.username}"
            elif grp.invite_link:
                chat_url = grp.invite_link
            else:
                try:
                    chat_url = await grp.export_invite_link()
                except Exception:
                    pass
        except Exception:
            pass

        if chat_url:
            try:
                await locked_msg.edit_reply_markup(
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Back to Game 🔙", url=chat_url)]]
                    )
                )
            except Exception:
                pass

        # Log to log group: bowler name, locked choice, group name
        try:
            log_text = (
                f"🔒 <b>Ball Locked</b>\n"
                f"👤 Bowler: <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>\n"
                f"🎯 Choice: <b>{val}</b>\n"
                f"📍 Group: <b>{group_title}</b>"
            )
            await context.bot.send_message(LOG_GROUP_ID, log_text, parse_mode="HTML")
        except Exception:
            pass

        await send_media_safely(
            context, group_id, MEDIA["batter_turn"],
            f"🚨 Ball delivered 🌀\n👇 <a href='tg://user?id={batter['id']}'>{batter['name']}</a>, type {hit_opts} to hit!🏏",
        )
        set_afk_timer(context, group_id, batter["id"], "BATTER")
        return

    # ── Group chat — BATTER input ─────────────────────────────────────────
    chat_id = update.effective_chat.id
    game    = context.bot_data.get(chat_id)
    if not game or game.get("state") != "PLAYING" or game.get("waiting_for") != "BATTER":
        return

    if game.get("mode") == "SOLO":
        if val < 1 or val > 6:
            return
        batter = game["players"][game["batter_idx"]]
        bowler = game["players"][game["bowler_idx"]]
    else:
        if val < 0 or val > 6:
            return
        batter = game.get("striker")
        bowler = game.get("current_bowler")

    if batter is None or bowler is None:
        return
    if update.effective_user.id != batter["id"]:
        return

    hit_val = val
    pause_time = 0
    game["waiting_for"] = "PROCESSING_BATTER"
    clear_afk_timer(context, chat_id)

    # ── SOLO: record batter's stats at start of this over (first ball only) ─
    if game.get("mode") == "SOLO":
        _snaps = game.setdefault("_over_batter_snapshots", {})
        _bid   = str(batter["id"])
        if _bid not in _snaps:
            _snaps[_bid] = {
                "name":        batter["name"],
                "runs_start":  batter.get("runs", 0),
                "balls_start": batter.get("balls_faced", 0),
            }

    if hit_val == 4:
        batter["match_4s"] = batter.get("match_4s", 0) + 1
        game["_over_4s"] = game.get("_over_4s", 0) + 1
    elif hit_val == 6:
        batter["match_6s"] = batter.get("match_6s", 0) + 1
        game["_over_6s"] = game.get("_over_6s", 0) + 1

    bowl_val         = game["current_bowl"]
    is_free_hit      = game.get("is_free_hit", False)
    is_legal_delivery = True

    # ── NO BALL ───────────────────────────────────────────────────────────
    if bowl_val == "NO_BALL":
        is_legal_delivery = False
        bowler["consecutive_wickets"] = 0
        batter["balls_faced"] = batter.get("balls_faced", 0) + 1
        game["is_free_hit"]   = True
        old_runs = batter.get("runs", 0)
        batter["runs"]    = old_runs + hit_val + 1
        bowler["conceded"] = bowler.get("conceded", 0) + hit_val + 1
        if game.get("mode") == "TEAM":
            game["batting_team_ref"]["score"] += hit_val + 1

        result_text = (
            f"🚨 <b>IT WAS A NO BALL!</b> 1 penalty run.\n"
            f"🚀 <b>NEXT BALL WILL BE A FREE HIT!</b> 🚀\n\n"
            f"🏏 Batter hit: <b>{hit_val}</b>\n\n"
        )
        if hit_val == 0:
            result_text += f"🛡️ <b>Solid defense! Dot ball.</b> ({batter['name']}: {batter['runs']} off {batter['balls_faced']})"
        else:
            result_text += f"🏃‍♂️ <b>Great shot! {hit_val} runs!</b> 🔥 ({batter['name']}: {batter['runs']} off {batter['balls_faced']})"

        await send_media_safely(context, chat_id, MEDIA.get(hit_val, MEDIA[0]), result_text, reply_to_message_id=update.message.message_id)
        if hit_val > 0:
            try:
                await context.bot.send_message(chat_id, random.choice(HIT_COMMENTARY.get(hit_val, HIT_COMMENTARY[1])), parse_mode="HTML")
            except Exception:
                pass

        if old_runs < 100 and batter["runs"] >= 100:
            try:
                await update_user_db(batter["id"], {"exp": 150})
            except Exception:
                pass
            await send_media_safely(context, chat_id, MEDIA["100"], f"👑 <b>CENTURY! TAKE A BOW!</b> 💯🔥\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> has smashed a glorious century!")
        elif old_runs < 50 and batter["runs"] >= 50:
            try:
                await update_user_db(batter["id"], {"exp": 50})
            except Exception:
                pass
            await send_media_safely(context, chat_id, MEDIA["50"], f"🏏 <b>HALF-CENTURY! BRILLIANT INNINGS!</b> 💥🙌\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> reaches 50!")

        if game.get("mode") == "TEAM" and hit_val % 2 != 0:
            swap_strike(game)
            try:
                await context.bot.send_message(
                    chat_id,
                    f"🔄 Strike rotated! 🏏 <a href='tg://user?id={game['striker']['id']}'>{game['striker']['name']}</a> is now on strike!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        if game.get("mode") == "TEAM" and game.get("innings") == 2 and game["batting_team_ref"]["score"] >= game.get("target", 0):
            await process_team_innings_end(context, chat_id, game)
            return

    # ── YORKER ────────────────────────────────────────────────────────────
    elif bowl_val == "YORKER":
        batter["balls_faced"] = batter.get("balls_faced", 0) + 1
        bowler["balls_bowled"] = bowler.get("balls_bowled", 0) + 1
        if game.get("mode") == "SOLO":
            game["balls_bowled"] += 1
        if game.get("mode") == "TEAM":
            game["bowling_team_ref"]["balls_bowled"] += 1

        survives = hit_val in ([0, 1, 2, 3] if game.get("mode") == "TEAM" else [1, 2, 3])

        if not survives:
            if is_free_hit:
                game["is_free_hit"] = False
                bowler["consecutive_wickets"] = 0
                game.setdefault("_over_ball_log", []).append("0")
                result_text = (
                    f"🥎 Bowler delivery: <b>YORKER</b>\n🏏 Batter hit: <b>{hit_val}</b>\n\n"
                    f"💥 <b>BOWLED! BUT IT'S A FREE HIT!</b> 😅\n"
                    f"<a href='tg://user?id={batter['id']}'>{batter['name']}</a> survives and scores 0 runs!"
                )
                await send_media_safely(context, chat_id, MEDIA["batter_turn"], result_text, reply_to_message_id=update.message.message_id)
            else:
                bowler["wickets"] = bowler.get("wickets", 0) + 1
                game.setdefault("_over_ball_log", []).append("W")
                await update_user_db(bowler["id"], {"exp": 20})
                result_text = (
                    f"🥎 Bowler delivery: <b>YORKER</b>\n🏏 Batter hit: <b>{hit_val}</b>\n\n"
                    f"💥 <b>HOWZAT! OUT! ❌ ❌</b> ☝️ {batter['name']} is bowled by a lethal yorker for {batter.get('runs', 0)}! 😔🚶‍♂️"
                )
                await send_media_safely(context, chat_id, MEDIA["yorker"], result_text, reply_to_message_id=update.message.message_id)
                if batter.get("runs", 0) == 0:
                    await send_media_safely(context, chat_id, MEDIA["duck"], f"🦆 <a href='tg://user?id={batter['id']}'>{batter['name']}</a> 💀 Duck!\nBro came to spectate and accidentally batted 🦆")
                _yorker_praise = [
                    f"🎯 What a YORKER! <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> is an absolute SNIPER with the ball! 🔥",
                    f"💥 LETHAL YORKER from <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>! A toe-crusher of the highest order!",
                    f"🏆 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> delivers the PERFECT yorker! The batter had absolutely NO chance!",
                    f"⚡ That yorker from <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> was utterly UNPLAYABLE! WHAT A DELIVERY! 🌟",
                    f"🎪 Full and fast, right into the blockhole! <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> is a certified GENIUS! 🧠",
                    f"🔥 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> has done it with the PERFECT yorker! That's world-class bowling!",
                    f"😱 The batter never even saw it! <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> is UNPLAYABLE right now!",
                    f"💣 EXPLOSIVE yorker from <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>! Aimed at the base and nailed it perfectly! 🎯",
                ]
                try:
                    await context.bot.send_message(chat_id, random.choice(_yorker_praise), parse_mode="HTML")
                except Exception:
                    pass

                bowler["consecutive_wickets"] = bowler.get("consecutive_wickets", 0) + 1
                if bowler["consecutive_wickets"] == 3:
                    bowler["consecutive_wickets"] = 0
                    await update_user_db(bowler["id"], {"hat_tricks": 1, "exp": 1000})
                    ht_vid = "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777819065/VID_20260503200210_rabpvn.mp4"
                    await send_media_safely(context, chat_id, ht_vid, f"🎩 <b>HATTT-TRICK!</b> <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>, you are a magician!! 🪄🔥")

                dismiss_batter(game, batter)
                if game.get("mode") == "TEAM":
                    game["batting_team_ref"]["wickets"] += 1
                    if game["batting_team_ref"]["wickets"] >= len(game["batting_team_ref"]["players"]) - 1:
                        await process_team_innings_end(context, chat_id, game)
                        return
                    game["waiting_for"] = "TEAM_BATTER_SELECT"
                    await context.bot.send_message(
                        chat_id,
                        "🏏 Captain/Host, type <code>/batting</code> to see batters list or <code>/batting [number]</code> to select the next batter.",
                        parse_mode="HTML",
                    )
                else:
                    game["batter_idx"] += 1
                    if game["batter_idx"] >= len(game["players"]):
                        await check_solo_winner_exp(game)
                        await save_match_history_to_db(context, chat_id, game)
                        await commit_player_stats(game)
                        game["state"] = "NOT_PLAYING"
                        await trigger_full_scorecard_message(context, chat_id, game)
                        return
                    if game["batter_idx"] == game["bowler_idx"]:
                        game["bowler_idx"] = (game["bowler_idx"] + 1) % len(game["players"])
                        game["balls_bowled"] = 0
                        game["special_used_this_over"] = False
        else:
            bowler["consecutive_wickets"] = 0
            if is_free_hit:
                game["is_free_hit"] = False
            old_runs = batter.get("runs", 0)
            batter["runs"]    = old_runs + hit_val
            bowler["conceded"] = bowler.get("conceded", 0) + hit_val
            if game.get("mode") == "TEAM":
                game["batting_team_ref"]["score"] += hit_val
            game.setdefault("_over_ball_log", []).append(str(hit_val))

            result_text = (
                f"🥎 Bowler delivery: <b>YORKER</b>\n🏏 Batter hit: <b>{hit_val}</b>\n\n"
                f"🏃‍♂️ <b>Great shot! Dug out the yorker for {hit_val} runs!</b> 🔥 "
                f"({batter['name']}: {batter['runs']} off {batter['balls_faced']})"
            )
            await send_media_safely(context, chat_id, MEDIA.get(hit_val, MEDIA[0]), result_text, reply_to_message_id=update.message.message_id)
            if hit_val > 0:
                try:
                    await context.bot.send_message(chat_id, random.choice(HIT_COMMENTARY.get(hit_val, HIT_COMMENTARY[1])), parse_mode="HTML")
                except Exception:
                    pass

            if old_runs < 100 and batter["runs"] >= 100:
                try:
                    await update_user_db(batter["id"], {"exp": 150})
                except Exception:
                    pass
                await send_media_safely(context, chat_id, MEDIA["100"], f"👑 <b>CENTURY! TAKE A BOW!</b> 💯🔥\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> has smashed a glorious century!")
            elif old_runs < 50 and batter["runs"] >= 50:
                try:
                    await update_user_db(batter["id"], {"exp": 50})
                except Exception:
                    pass
                await send_media_safely(context, chat_id, MEDIA["50"], f"🏏 <b>HALF-CENTURY! BRILLIANT INNINGS!</b> 💥🙌\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> reaches 50!")

            if game.get("mode") == "TEAM":
                if game.get("innings") == 2 and game["batting_team_ref"]["score"] >= game.get("target", 0):
                    await process_team_innings_end(context, chat_id, game)
                    return
                if hit_val % 2 != 0:
                    swap_strike(game)
                    try:
                        await context.bot.send_message(
                            chat_id,
                            f"🔄 Strike rotated! 🏏 <a href='tg://user?id={game['striker']['id']}'>{game['striker']['name']}</a> is now on strike!",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

    # ── Normal delivery — SAME NUMBER = OUT ───────────────────────────────
    elif str(hit_val) == str(bowl_val):
        batter["balls_faced"] = batter.get("balls_faced", 0) + 1
        bowler["balls_bowled"] = bowler.get("balls_bowled", 0) + 1
        if game.get("mode") == "SOLO":
            game["balls_bowled"] += 1
        if game.get("mode") == "TEAM":
            game["bowling_team_ref"]["balls_bowled"] += 1

        if is_free_hit:
            game["is_free_hit"] = False
            bowler["consecutive_wickets"] = 0
            game.setdefault("_over_ball_log", []).append("0")
            result_text = (
                f"🥎 Bowler delivery: <b>{bowl_val}</b>\n🏏 Batter hit: <b>{hit_val}</b>\n\n"
                f"💥 <b>BOWLED! BUT IT'S A FREE HIT!</b> 😅\n"
                f"<a href='tg://user?id={batter['id']}'>{batter['name']}</a> survives and scores 0 runs!"
            )
            await send_media_safely(context, chat_id, MEDIA["batter_turn"], result_text, reply_to_message_id=update.message.message_id)
        else:
            bowler["wickets"] = bowler.get("wickets", 0) + 1
            game.setdefault("_over_ball_log", []).append("W")
            await update_user_db(bowler["id"], {"exp": 20})
            result_text = (
                f"🥎 Bowler delivery: <b>{bowl_val}</b>\n🏏 Batter hit: <b>{hit_val}</b>\n\n"
                f"💥 <b>HOWZAT! OUT!❌ ❌</b> ☝️ {batter['name']} is dismissed for {batter.get('runs', 0)}! 😔🤸🏻\n"
                f"{batter['name']} KOI NA HOTA HAI !!"
            )
            await send_media_safely(context, chat_id, MEDIA["out"], result_text, reply_to_message_id=update.message.message_id)
            if batter.get("runs", 0) == 0:
                await send_media_safely(context, chat_id, MEDIA["duck"], f"🦆 <a href='tg://user?id={batter['id']}'>{batter['name']}</a> got a duck 🦆")
            _fielding_pool = []
            if game.get("mode") == "TEAM":
                _fielding_pool = [p for p in game.get("bowling_team_ref", {}).get("players", []) if p["id"] != bowler["id"]]
            else:
                _fielding_pool = [p for p in game.get("players", []) if p["id"] not in {batter["id"], bowler["id"]}]
            if _fielding_pool:
                _catcher = random.choice(_fielding_pool)
                # Track catches on the player dict and persist to DB
                _catcher["catches"] = _catcher.get("catches", 0) + 1
                try:
                    await update_user_db(_catcher["id"], {"catches": 1})
                except Exception:
                    pass
                _catch_lines = [
                    f"🧤 CAUGHT! <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a> takes a STUNNING catch! What reflexes! 🌟",
                    f"😱 <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a> dives to his right and holds on! SCREAMER of a catch! 🎯",
                    f"🏆 WORLDCLASS fielding from <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a>! That is UNBELIEVABLE! 👏",
                    f"💪 <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a> takes the catch and the team goes absolutely WILD! 🔥",
                    f"🎪 What a grab from <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a>! Not everyone can pull that off! 🧤✨",
                    f"⚡ <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a> completes the catch to PERFECTION! Clinical fielding! 🎯",
                    f"🌟 Superb catch by <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a>! Safe as houses! The batter has to walk! 🚶",
                    f"😤 <a href='tg://user?id={_catcher['id']}'>{_catcher['name']}</a> wasn't going to drop that one! Iron hands! 💎",
                ]
                try:
                    await context.bot.send_message(chat_id, random.choice(_catch_lines), parse_mode="HTML")
                except Exception:
                    pass
            _bowler_dismiss_lines = [
                f"🏆 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> is absolutely ROLLING! What a wicket! 🔥",
                f"🥎 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> gets the breakthrough! The whole team is PUMPED! 💪",
                f"😤 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> outthought the batter! Pure bowling genius! 🎯",
                f"🌟 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> strikes! That is why you always respect the ball! 🔥",
                f"⚡ Wicket for <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>! Absolutely unplayable delivery! 💥",
                f"🎪 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> has the batter in all sorts of trouble — and now it's OVER for them!",
                f"🧠 Smart bowling from <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>! Set the batter up perfectly and executed it beautifully!",
                f"💣 <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a> is on FIRE! Another one bites the dust! 🔥",
            ]
            try:
                await context.bot.send_message(chat_id, random.choice(_bowler_dismiss_lines), parse_mode="HTML")
            except Exception:
                pass

            bowler["consecutive_wickets"] = bowler.get("consecutive_wickets", 0) + 1
            if bowler["consecutive_wickets"] == 3:
                bowler["consecutive_wickets"] = 0
                try:
                    await update_user_db(bowler["id"], {"hat_tricks": 1, "exp": 1000})
                except Exception:
                    pass
                ht_vid = "https://res.cloudinary.com/dxgfxfoog/video/upload/v1777819065/VID_20260503200210_rabpvn.mp4"
                await send_media_safely(context, chat_id, ht_vid, f"🎩 <b>HAT-TRICK!</b> <a href='tg://user?id={bowler['id']}'>{bowler['name']}</a>, you are a magician!! 🪄🔥")

            dismiss_batter(game, batter)
            if game.get("mode") == "TEAM":
                game["batting_team_ref"]["wickets"] += 1
                if game["batting_team_ref"]["wickets"] >= len(game["batting_team_ref"]["players"]) - 1:
                    await process_team_innings_end(context, chat_id, game)
                    return
                game["waiting_for"] = "TEAM_BATTER_SELECT"
                await context.bot.send_message(
                    chat_id,
                    "🏏 Captain/Host, type <code>/batting</code> to see batters list or <code>/batting [number]</code> to select the next batter.",
                    parse_mode="HTML",
                )
            else:
                game["batter_idx"] += 1
                if game["batter_idx"] >= len(game["players"]):
                    await check_solo_winner_exp(game)
                    await save_match_history_to_db(context, chat_id, game)
                    await commit_player_stats(game)
                    game["state"] = "NOT_PLAYING"
                    await trigger_full_scorecard_message(context, chat_id, game)
                    return
                if game["batter_idx"] == game["bowler_idx"]:
                    game["bowler_idx"] = (game["bowler_idx"] + 1) % len(game["players"])
                    game["balls_bowled"] = 0
                    game["special_used_this_over"] = False

    # ── Normal delivery — DIFFERENT NUMBER = RUNS ─────────────────────────
    else:
        bowler["consecutive_wickets"] = 0
        batter["balls_faced"]  = batter.get("balls_faced", 0) + 1
        bowler["balls_bowled"] = bowler.get("balls_bowled", 0) + 1
        if game.get("mode") == "SOLO":
            game["balls_bowled"] += 1
        if game.get("mode") == "TEAM":
            game["bowling_team_ref"]["balls_bowled"] += 1
        if is_free_hit:
            game["is_free_hit"] = False

        old_runs = batter.get("runs", 0)
        batter["runs"]    = old_runs + hit_val
        bowler["conceded"] = bowler.get("conceded", 0) + hit_val
        if game.get("mode") == "TEAM":
            game["batting_team_ref"]["score"] += hit_val
        game.setdefault("_over_ball_log", []).append(str(hit_val))

        if hit_val == 0:
            result_text = f"🏏 Batter hit: <b>{hit_val}</b>\n\n🛡️ <b>Solid defense! Dot ball.</b> ({batter['name']}: {batter['runs']} off {batter['balls_faced']})"
        else:
            result_text = f"🏏 Batter hit: <b>{hit_val}</b>\n\n🏃‍♂️ <b>Great shot! {hit_val} runs!</b> 🔥 ({batter['name']}: {batter['runs']} off {batter['balls_faced']})"

        await send_media_safely(context, chat_id, MEDIA.get(hit_val, MEDIA[0]), result_text, reply_to_message_id=update.message.message_id)

        # ── TEAM MODE: 4 consecutive zeros → instant YORKER OUT ──────────────
        if game.get("mode") == "TEAM" and not is_free_hit:
            if hit_val == 0:
                batter["_consec_zeros"] = batter.get("_consec_zeros", 0) + 1
            else:
                batter["_consec_zeros"] = 0

            if batter.get("_consec_zeros", 0) >= 4:
                batter["_consec_zeros"] = 0
                bowler["wickets"] = bowler.get("wickets", 0) + 1
                game.setdefault("_over_ball_log", []).append("W")
                try:
                    await update_user_db(bowler["id"], {"exp": 20})
                except Exception:
                    pass
                await send_media_safely(
                    context, chat_id, MEDIA["yorker"],
                    f"⚠️ <b>4 CONSECUTIVE DOT BALLS!</b> 🎯\n\n"
                    f"💥 <b>YORKER SPECIAL!</b> The bowler unleashes a thunderbolt YORKER!\n"
                    f"❌ <b>{batter['name']} is OUT!</b> — Couldn't score 4 balls in a row, and now pays the price! 😤🚶‍♂️",
                )
                dismiss_batter(game, batter)
                game["batting_team_ref"]["wickets"] += 1
                if game["batting_team_ref"]["wickets"] >= len(game["batting_team_ref"]["players"]) - 1:
                    await process_team_innings_end(context, chat_id, game)
                    return
                game["waiting_for"] = "TEAM_BATTER_SELECT"
                await context.bot.send_message(
                    chat_id,
                    "🏏 Captain/Host, type <code>/batting</code> to see batters list or <code>/batting [number]</code> to select the next batter.",
                    parse_mode="HTML",
                )
                return

        if hit_val > 0:
            try:
                await context.bot.send_message(chat_id, random.choice(HIT_COMMENTARY.get(hit_val, HIT_COMMENTARY[1])), parse_mode="HTML")
            except Exception:
                pass

        if old_runs < 100 and batter["runs"] >= 100:
            try:
                await update_user_db(batter["id"], {"exp": 150})
            except Exception:
                pass
            await send_media_safely(context, chat_id, MEDIA["100"], f"👑 <b>CENTURY! TAKE A BOW!</b> 💯🔥\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> has smashed a glorious century!")
        elif old_runs < 50 and batter["runs"] >= 50:
            try:
                await update_user_db(batter["id"], {"exp": 50})
            except Exception:
                pass
            await send_media_safely(context, chat_id, MEDIA["50"], f"🏏 <b>HALF-CENTURY! BRILLIANT INNINGS!</b> 💥🙌\n<a href='tg://user?id={batter['id']}'>{batter['name']}</a> reaches 50!")

        if game.get("mode") == "TEAM":
            if game.get("innings") == 2 and game["batting_team_ref"]["score"] >= game.get("target", 0):
                await process_team_innings_end(context, chat_id, game)
                return
            if hit_val % 2 != 0:
                swap_strike(game)
                try:
                    await context.bot.send_message(
                        chat_id,
                        f"🔄 Strike rotated! 🏏 <a href='tg://user?id={game['striker']['id']}'>{game['striker']['name']}</a> is now on strike!",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    # ── End-of-over check ─────────────────────────────────────────────────
    is_over_complete = False
    if is_legal_delivery:
        if game.get("mode") == "SOLO" and game.get("balls_bowled", 0) >= game.get("spell", 6):
            is_over_complete = True
        elif game.get("mode") == "TEAM":
            bb = game["bowling_team_ref"]["balls_bowled"]
            if bb > 0 and bb % 6 == 0:
                is_over_complete = True

    if is_over_complete:
        spell_text = f"🔁 <b>Over Completed!</b> 🛑 {bowler['name']} finished.\n"
        if game.get("mode") == "TEAM":
            _sb = bowler.get("balls_bowled", 0) - bowler.get("_spell_balls0", 0)
            _sr = bowler.get("conceded", 0)      - bowler.get("_spell_runs0", 0)
            _sw = bowler.get("wickets", 0)       - bowler.get("_spell_wkts0", 0)
            # ── TEAM Over Summary ──────────────────────────────────────────
            batting_team   = game["batting_team_ref"]
            completed_over = game["bowling_team_ref"]["balls_bowled"] // 6
            total_overs    = game.get("target_overs", "?")

            _over_4s = game.get("_over_4s", 0)
            _over_6s = game.get("_over_6s", 0)

            _ball_log     = game.get("_over_ball_log", [])
            _ball_log_str = " | ".join(_ball_log) if _ball_log else "—"

            over_summary = (
                f"\n"
                f"╔══🏏 <b>OVER {completed_over}/{total_overs}</b> 🏏 ══╗\n"
                f"┃ 📊 <b>Score:</b> {batting_team['score']}/{batting_team['wickets']}\n"
                f"┃\n"
                f"┃ 🎳 <b>{bowler['name'][:12]}</b>\n"
                f"┃    Runs: <b>{_sr}</b>\n"
                f"┃    Wkts: <b>{_sw}</b>\n"
                f"┃\n"
                f"┃ 🔢 <b>THIS OVER</b>\n"
                f"┃    {_sr}R | {_sw}W\n"
                f"┃    4️⃣ {_over_4s} | 6️⃣ {_over_6s}\n"
                f"┃    🎯 {_ball_log_str}\n"
            )

            if game.get("innings") == 2:
                target    = game.get("target", 0)
                runs_left = max(0, target - batting_team["score"])
                balls_rem = (
                    game.get("target_overs", 0) * 6
                    - game["bowling_team_ref"]["balls_bowled"]
                )
                if balls_rem > 0:
                    rrr = (runs_left * 6) / balls_rem
                    over_summary += (
                        f"┃\n"
                        f"┃ 🎯 <b>CHASE</b>\n"
                        f"┃    Need: {runs_left}({balls_rem})\n"
                        f"┃    RRR: <b>{rrr:.2f}</b>\n"
                    )

            if game.get("striker") or game.get("non_striker"):
                over_summary += (
                    f"┃\n"
                    f"┃ 🏏 <b>BATTERS</b>\n"
                )
                if game.get("striker"):
                    s  = game["striker"]
                    sr = s.get("runs", 0) * 100 / max(1, s.get("balls_faced", 1))
                    over_summary += (
                        f"┃ 👉🏻 {s['name'][:12]} (*)\n"
                        f"┃    {s['runs']}({s['balls_faced']})\n"
                        f"┃    SR: {sr:.0f}\n"
                    )
                if game.get("non_striker"):
                    ns  = game["non_striker"]
                    nsr = ns.get("runs", 0) * 100 / max(1, ns.get("balls_faced", 1))
                    over_summary += (
                        f"┃ • {ns['name'][:12]}\n"
                        f"┃    {ns['runs']}({ns['balls_faced']})\n"
                        f"┃    SR: {nsr:.0f}\n"
                    )

            over_summary += "╚════════════════╝"
            spell_text = over_summary
            # reset per-over counters for next over
            game["_over_4s"] = 0
            game["_over_6s"] = 0
            game["_over_ball_log"] = []
            # ── end over summary ──────────────────────────────────────────
            if _sb > 0:
                bowler.setdefault("bowling_spells", []).append({"b": _sb, "r": _sr, "w": _sw})
            for _k in ("_spell_balls0", "_spell_runs0", "_spell_wkts0"):
                bowler.pop(_k, None)
            swap_strike(game)
            game["last_bowler_id"]         = bowler["id"]
            game["special_used_this_over"] = False
            if game["bowling_team_ref"]["balls_bowled"] >= game.get("target_overs", 0) * 6:
                await process_team_innings_end(context, chat_id, game)
                return
            # Set state BEFORE any awaits so /bowling is accepted immediately
            # when the captain reacts to the "select next bowler" message.
            # Previously this was set AFTER two awaits, causing "already bowling"
            # errors because waiting_for was still "PROCESSING_BATTER" during them.
            if game.get("waiting_for") == "TEAM_BATTER_SELECT":
                game["need_new_bowler"] = True
            else:
                game["waiting_for"] = "TEAM_BOWLER_SELECT"
                game["current_bowler"] = None
            await trigger_full_scorecard_message(context, chat_id, game)
            if game.get("striker"):
                spell_text += f"\n🔄 Strike rotated! 🏏 <a href='tg://user?id={game['striker']['id']}'>{game['striker']['name']}</a> is on strike!\n"
            spell_text += "\nBowling Captain/Host, select next bowler using <code>/bowling</code> to see list or <code>/bowling [num]</code>."
            await context.bot.send_message(chat_id, spell_text, parse_mode="HTML")
        else:
            _sb = bowler.get("balls_bowled", 0) - bowler.get("_spell_balls0", 0)
            _sr = bowler.get("conceded", 0)      - bowler.get("_spell_runs0", 0)
            _sw = bowler.get("wickets", 0)       - bowler.get("_spell_wkts0", 0)
            # ── SOLO Over Summary ──────────────────────────────────────────
            _spell_len  = game.get("spell", 6)
            _cur_batter = game["players"][game["batter_idx"]]
            _balls_done = _cur_batter.get("balls_faced", 0)
            _overs_done = _balls_done // _spell_len
            _over_4s    = game.get("_over_4s", 0)
            _over_6s    = game.get("_over_6s", 0)
            _snaps      = game.get("_over_batter_snapshots", {})
            _ball_log     = game.get("_over_ball_log", [])
            _ball_log_str = " | ".join(_ball_log) if _ball_log else "—"

            solo_over_summary = (
                f"\n"
                f"╔═══ 🏏 <b>OVER {_overs_done}</b> 🏏 ═══╗\n"
                f"┃\n"
                f"┃ 🎳 <b>{bowler['name'][:12]}</b>\n"
                f"┃    Runs: <b>{_sr}</b>\n"
                f"┃    Wkts: <b>{_sw}</b>\n"
                f"┃\n"
                f"┃  👀<b>THIS OVER</b>\n"
                f"┃    {_sr}R | {_sw}W\n"
                f"┃    4s: {_over_4s} | 6s: {_over_6s}\n"
                f"┃    🎯 {_ball_log_str}\n"
                f"┃\n"
                f"┃ 🏏 <b>BATTERS THIS OVER</b>\n"
            )
            # Show each batter who faced a ball this over
            for _pid, _snap in _snaps.items():
                _p = next((x for x in game["players"] if str(x["id"]) == _pid), None)
                if _p:
                    _ov_runs  = _p.get("runs", 0)  - _snap["runs_start"]
                    _ov_balls = _p.get("balls_faced", 0) - _snap["balls_start"]
                    _psr      = _ov_runs * 100 / max(1, _ov_balls) if _ov_balls > 0 else 0
                    _out_tag  = " ❌" if _p.get("is_out") else " 🟢"
                    _is_cur   = str(_p["id"]) == str(_cur_batter.get("id", "")) and not _p.get("is_out")
                    _striker_tag = " (*)" if _is_cur else ""
                    solo_over_summary += (
                        f"┃ ⭐ {_p['name'][:12]}{_striker_tag}{_out_tag}\n"
                        f"┃    {_ov_runs}({_ov_balls}) SR:{_psr:.0f}\n"
                    )
            solo_over_summary += "╚════════════════╝"

            spell_text = solo_over_summary
            # reset per-over counters + batter snapshots for next over
            game["_over_4s"] = 0
            game["_over_6s"] = 0
            game["_over_ball_log"] = []
            game["_over_batter_snapshots"] = {}
            # ── end over summary ──────────────────────────────────────────
            if _sb > 0:
                bowler.setdefault("bowling_spells", []).append({"b": _sb, "r": _sr, "w": _sw})
            for _k in ("_spell_balls0", "_spell_runs0", "_spell_wkts0"):
                bowler.pop(_k, None)
            await trigger_full_scorecard_message(context, chat_id, game)
            await context.bot.send_message(chat_id, spell_text, parse_mode="HTML")
            game["balls_bowled"]           = 0
            game["special_used_this_over"] = False
            game["bowler_idx"]             = (game["bowler_idx"] + 1) % len(game["players"])
            if game["bowler_idx"] == game["batter_idx"]:
                game["bowler_idx"] = (game["bowler_idx"] + 1) % len(game["players"])
            _nb = game["players"][game["bowler_idx"]]
            _nb["_spell_balls0"] = _nb.get("balls_bowled", 0)
            _nb["_spell_runs0"]  = _nb.get("conceded", 0)
            _nb["_spell_wkts0"]  = _nb.get("wickets", 0)
            if game.get("state") == "PLAYING":
                game["waiting_for"] = "BOWLER"
    else:
        if game.get("state") == "PLAYING" and game.get("waiting_for") == "PROCESSING_BATTER":
            game["waiting_for"] = "BOWLER"

    # Safety net (Bug 2 fix): if state is still stuck, force-advance to BOWLER
    if game.get("state") == "PLAYING" and game.get("waiting_for") == "PROCESSING_BATTER":
        game["waiting_for"] = "BOWLER"

    if game.get("state") == "PLAYING" and game.get("waiting_for") == "BOWLER":
        await maybe_send_chase_message(context, chat_id, game)
        await asyncio.sleep(0.4)
        try:
            await trigger_bowl(context, chat_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Chase message helper
# ---------------------------------------------------------------------------

async def maybe_send_chase_message(context, chat_id, game):
    if game.get("mode") != "TEAM" or game.get("innings") != 2:
        return
    target = game.get("target", 0)
    bat_score = game.get("batting_team_ref", {}).get("score", 0)
    runs_needed = target - bat_score
    if runs_needed <= 0 or runs_needed >= 30:
        return
    balls_bowled = game.get("bowling_team_ref", {}).get("balls_bowled", 0)
    total_balls = game.get("target_overs", 0) * 6
    balls_remaining = total_balls - balls_bowled
    if balls_remaining <= 0:
        return
    overs_full = balls_remaining // 6
    balls_extra = balls_remaining % 6
    if balls_extra > 0:
        overs_text = f"{overs_full}.{balls_extra} overs"
    else:
        overs_text = f"{overs_full} overs"
    await context.bot.send_message(
        chat_id,
        f"🎯 <b>{runs_needed} runs needed off {balls_remaining} balls ({overs_text})!</b> ",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /ranking command — Hall of Fame
# ---------------------------------------------------------------------------

async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [
            InlineKeyboardButton("🦆 Duck Ranking",       callback_data="rank_ducks"),
            InlineKeyboardButton("💥 Sixes Ranking",      callback_data="rank_sixes"),
        ],
        [
            InlineKeyboardButton("🥎 Wickets Ranking",    callback_data="rank_wickets"),
            InlineKeyboardButton("🏃 Total Runs",         callback_data="rank_runs"),
        ],
        [
            InlineKeyboardButton("⚡ Strike Rate",        callback_data="rank_sr"),
            InlineKeyboardButton("🎩 Hat-tricks",         callback_data="rank_hattricks"),
        ],
        [
            InlineKeyboardButton("💯 Centuries",          callback_data="rank_centuries"),
            InlineKeyboardButton("🌟 Half-Centuries",     callback_data="rank_fifties"),
        ],
        [
            InlineKeyboardButton("🏆 Most Runs in Match", callback_data="rank_most_runs_match"),
        ],
        [
            InlineKeyboardButton("🧤 Most Catches",       callback_data="rank_catches"),
        ],
    ]
    await update.message.reply_text(
        "🏆 <b>WELCOME TO THE HALL OF FAME!</b> 🏆\n\n"
        "This is where legends are remembered.\n"
        "The greatest performers in our arena live here forever.\n\n"
        "🌟 Select a category to see the Top 10:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML",
    )


def _make_player_link(uid, name):
    """Return a Telegram clickable mention link for a player."""
    return f"<a href='tg://user?id={uid}'>{name}</a>"


async def _send_ranking(query, title: str, field: str, label: str, fmt=None):
    if users_col is None:
        await query.edit_message_text("❌ Database not connected.")
        return
    requester_id = query.from_user.id
    docs = await users_col.find({field: {"$gt": 0}}).to_list(length=None)
    total_players = len(docs)
    random.shuffle(docs)
    docs.sort(key=lambda x: x.get(field, 0), reverse=True)
    top = docs[:10]

    # Find requester's rank
    requester_rank = None
    requester_doc  = None
    for idx, p in enumerate(docs):
        if p.get("user_id") == requester_id:
            requester_rank = idx + 1
            requester_doc  = p
            break

    if not top:
        lines = "😶 No one has recorded a score here yet!"
    else:
        lines = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(top):
            uid   = p.get("user_id", 0)
            name  = p.get("first_name", "Player")
            link  = _make_player_link(uid, name)
            value = p.get(field, 0)
            medal = medals[i] if i < 3 else f"<b>#{i+1}</b>"
            lines += f"{medal} {link} — <b>{value}</b> {label}\n"

    your_rank_line = ""
    if requester_doc:
        your_val = requester_doc.get(field, 0)
        your_link = _make_player_link(requester_id, requester_doc.get("first_name", "You"))
        your_rank_line = f"\n👤 <b>Your Rank: #{requester_rank}</b> — {your_link} — <b>{your_val}</b> {label}\n"

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="rank_main")]])
    await query.edit_message_text(
        f"🏆 <b>{title}</b> (Total Players: {total_players})\n"
        f"{your_rank_line}"
        f"━━━━━━━━━━━━━━━━━\n{lines}\n━━━━━━━━━━━━━━━━━\n🏏 <i>Ties broken randomly — keep playing!</i>",
        reply_markup=back_kb,
        parse_mode="HTML",
    )


async def _send_sr_ranking(query):
    if users_col is None:
        await query.edit_message_text("❌ Database not connected.")
        return
    requester_id = query.from_user.id
    docs = await users_col.find({
        "$expr": {"$gte": [{"$add": [{"$ifNull": ["$solo_matches", 0]}, {"$ifNull": ["$team_matches", 0]}]}, 20]}
    }).to_list(length=None)
    total_players = len(docs)
    random.shuffle(docs)
    docs.sort(key=lambda x: (x.get("total_runs", 0) / x.get("balls_faced", 1)) * 100, reverse=True)
    top = docs[:10]

    requester_rank = None
    requester_doc  = None
    for idx, p in enumerate(docs):
        if p.get("user_id") == requester_id:
            requester_rank = idx + 1
            requester_doc  = p
            break

    if not top:
        lines = "😶 Not enough data yet!"
    else:
        lines = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(top):
            uid  = p.get("user_id", 0)
            name = p.get("first_name", "Player")
            link = _make_player_link(uid, name)
            sr   = (p.get("total_runs", 0) / p.get("balls_faced", 1)) * 100
            medal = medals[i] if i < 3 else f"<b>#{i+1}</b>"
            lines += f"{medal} {link} — <b>SR: {sr:.1f}</b>\n"

    your_rank_line = ""
    if requester_doc:
        your_sr   = (requester_doc.get("total_runs", 0) / requester_doc.get("balls_faced", 1)) * 100
        your_link = _make_player_link(requester_id, requester_doc.get("first_name", "You"))
        your_rank_line = f"\n👤 <b>Your Rank: #{requester_rank}</b> — {your_link} — <b>SR: {your_sr:.1f}</b>\n"

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="rank_main")]])
    await query.edit_message_text(
        f"🏆 <b>⚡ STRIKE RATE RANKING</b> (min 20 balls — Total Players: {total_players})\n"
        f"{your_rank_line}"
        f"━━━━━━━━━━━━━━━━━\n{lines}\n━━━━━━━━━━━━━━━━━\n🏏 <i>Ties broken randomly — keep playing!</i>",
        reply_markup=back_kb,
        parse_mode="HTML",
    )


async def _send_most_runs_in_match_ranking(query):
    if users_col is None:
        await query.edit_message_text("❌ Database not connected.")
        return
    requester_id = query.from_user.id
    docs = await users_col.find({"highest_score.runs": {"$gt": 0}}).to_list(length=None)
    total_players = len(docs)
    random.shuffle(docs)
    docs.sort(key=lambda x: x.get("highest_score", {}).get("runs", 0), reverse=True)
    top = docs[:10]

    requester_rank = None
    requester_doc  = None
    for idx, p in enumerate(docs):
        if p.get("user_id") == requester_id:
            requester_rank = idx + 1
            requester_doc  = p
            break

    if not top:
        lines = "😶 No one has recorded a high score yet!"
    else:
        lines = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(top):
            uid   = p.get("user_id", 0)
            name  = p.get("first_name", "Player")
            link  = _make_player_link(uid, name)
            hs    = p.get("highest_score", {})
            runs  = hs.get("runs", 0)
            balls = hs.get("balls", 0)
            medal = medals[i] if i < 3 else f"<b>#{i+1}</b>"
            lines += f"{medal} {link} — <b>{runs} runs</b> ({balls} balls)\n"

    your_rank_line = ""
    if requester_doc:
        your_hs    = requester_doc.get("highest_score", {})
        your_link  = _make_player_link(requester_id, requester_doc.get("first_name", "You"))
        your_rank_line = (
            f"\n👤 <b>Your Rank: #{requester_rank}</b> — {your_link} — "
            f"<b>{your_hs.get('runs', 0)} runs</b> ({your_hs.get('balls', 0)} balls)\n"
        )

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="rank_main")]])
    await query.edit_message_text(
        f"🏆 <b>🏆 MOST RUNS IN A MATCH — TOP 10</b> (Total Players: {total_players})\n"
        f"{your_rank_line}"
        f"━━━━━━━━━━━━━━━━━\n{lines}\n━━━━━━━━━━━━━━━━━\n🏏 <i>Ties broken randomly — keep playing!</i>",
        reply_markup=back_kb,
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Tournament management commands (owner only)
# ---------------------------------------------------------------------------

async def tournament_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /tournament <Tournament Name>")
        return
    if tournaments_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    name = " ".join(context.args)
    existing = await tournaments_col.find_one({"name": name})
    if existing:
        await update.message.reply_text(f"⚠️ A tournament named <b>{name}</b> already exists!", parse_mode="HTML")
        return
    await tournaments_col.insert_one({
        "name": name,
        "created_by": update.effective_user.id,
        "registration_open": False,
        "teams": [],
    })
    await update.message.reply_text(
        f"🏆 Tournament <b>{name}</b> created successfully!\n"
        f"Use /regisopen to open registrations.",
        parse_mode="HTML",
    )


async def regisopen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    context.bot_data["registration_open"] = True
    await update.message.reply_text(
        "✅ <b>REGISTRATION IS NOW OPEN!</b>\n\n"
        "Players can DM the bot and use /register to register their team. 🏏",
        parse_mode="HTML",
    )


async def regisclose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    context.bot_data["registration_open"] = False
    await update.message.reply_text(
        "🔒 <b>REGISTRATION IS NOW CLOSED!</b>\n\n"
        "No more teams can register at this time.",
        parse_mode="HTML",
    )


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("📩 Please DM the bot to register your team!")
        return
    if not context.bot_data.get("registration_open"):
        await update.message.reply_text("🔒 Registrations are currently <b>CLOSED</b>. Stay tuned!", parse_mode="HTML")
        return
    if tourteams_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    context.user_data["reg_state"] = "team_name"
    context.user_data["reg_data"]  = {}
    await update.message.reply_text(
        "🏏 <b>TEAM REGISTRATION</b> 🏏\n\n"
        "Let's get your team registered! Step 1️⃣\n\n"
        "📝 Please send your <b>Team Name</b>:",
        parse_mode="HTML",
    )


async def tourteams_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if tourteams_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    teams = await tourteams_col.find({}).sort("team_number", 1).to_list(length=200)
    if not teams:
        await update.message.reply_text("📋 No teams registered yet.")
        return
    text = "📋 <b>REGISTERED TEAMS</b>\n\n"
    for t in teams:
        text += f"<b>#{t.get('team_number', '?')}</b> — {t.get('team_name', 'Unknown')}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...[Truncated]"
    await update.message.reply_text(text, parse_mode="HTML")


async def deleteteam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deleteteam <team number>\nExample: /deleteteam 3")
        return
    if tourteams_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    team_num = int(context.args[0])
    team = await tourteams_col.find_one({"team_number": team_num})
    if not team:
        await update.message.reply_text(f"❌ No team found with number <b>{team_num}</b>.", parse_mode="HTML")
        return
    await tourteams_col.delete_one({"team_number": team_num})
    await update.message.reply_text(
        f"🗑️ Team <b>#{team_num} — {team.get('team_name', 'Unknown')}</b> has been deleted from the tournament.",
        parse_mode="HTML",
    )


async def allteams_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if tourteams_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    teams = await tourteams_col.find({}).sort("team_number", 1).to_list(length=200)
    if not teams:
        await update.message.reply_text("📋 No teams registered yet.")
        return
    for t in teams:
        text = (
            f"🏏 <b>Team #{t.get('team_number', '?')}: {t.get('team_name', 'Unknown')}</b>\n\n"
            f"👑 Captain: {t.get('captain', 'N/A')}\n"
            f"🥈 Vice-Captain: {t.get('vc', 'N/A')}\n"
            f"🌟 Retention 1: {t.get('ret1', 'N/A')}\n"
            f"🌟 Retention 2: {t.get('ret2', 'N/A')}\n"
        )
        try:
            if t.get("logo_file_id"):
                await update.message.reply_photo(photo=t["logo_file_id"], caption=text, parse_mode="HTML")
            else:
                await update.message.reply_text(text, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(text, parse_mode="HTML")
        await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# /cachemedia command — Owner only, caches all media file_ids in MongoDB
# ---------------------------------------------------------------------------

async def cachemedia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if media_cache_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    # Collect all unique URLs from MEDIA dict
    all_urls = set()
    for v in MEDIA.values():
        if isinstance(v, str) and v.startswith("http"):
            all_urls.add(v)

    # Also add any extra static HTTP URLs used elsewhere in the bot
    # NOTE: TEAMS_ROSTER_IMG is a Telegram file_id (not a URL), so it is excluded
    extra_urls = [
        "https://media.giphy.com/media/hGJTJqTNaj0XXkLXZr/giphy.gif",
        "https://res.cloudinary.com/dxgfxfoog/image/upload/v1777818873/file_00000000fa6871fa8d9b30faff9899ae_hbyn9j.png",
    ]
    for url in extra_urls:
        if url and isinstance(url, str) and url.startswith("http"):
            all_urls.add(url)

    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(
        f"⏳ Caching {len(all_urls)} media files... Please wait.",
        parse_mode="HTML",
    )

    cached_count = 0
    already_count = 0
    failed_count = 0
    lines = []

    for url in all_urls:
        short = url.split("/")[-1][:40]
        # Check if already cached
        existing = await media_cache_col.find_one({"url": url})
        if existing and existing.get("file_id"):
            already_count += 1
            lines.append(f"✅ Already stored: <code>{short}</code>")
            continue
        try:
            # Determine type and send to get the file_id from Telegram
            if url.endswith(".gif") or "giphy.com" in url:
                sent = await context.bot.send_animation(
                    chat_id=chat_id, animation=url, caption="Caching...",
                    read_timeout=30, write_timeout=30,
                )
                media_type     = "animation"
                file_id        = sent.animation.file_id
                file_unique_id = sent.animation.file_unique_id
                await sent.delete()
            elif any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                sent = await context.bot.send_photo(
                    chat_id=chat_id, photo=url, caption="Caching...",
                    read_timeout=30, write_timeout=30,
                )
                media_type     = "photo"
                file_id        = sent.photo[-1].file_id
                file_unique_id = sent.photo[-1].file_unique_id
                await sent.delete()
            else:
                sent = await context.bot.send_video(
                    chat_id=chat_id, video=url, caption="Caching...",
                    read_timeout=30, write_timeout=30,
                )
                media_type     = "video"
                file_id        = sent.video.file_id
                file_unique_id = sent.video.file_unique_id
                await sent.delete()

            await media_cache_col.update_one(
                {"url": url},
                {"$set": {
                    "url": url,
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "media_type": media_type,
                }},
                upsert=True,
            )
            cached_count += 1
            lines.append(f"📦 Stored ({media_type}): <code>{short}</code>")
        except Exception as e:
            print(f"Failed to cache {url}: {e}")
            failed_count += 1
            lines.append(f"❌ Failed: <code>{short}</code>")

    summary = (
        f"✅ <b>Media caching complete!</b>\n"
        f"📦 Newly stored: <b>{cached_count}</b>\n"
        f"♻️ Already stored: <b>{already_count}</b>\n"
        f"❌ Failed: <b>{failed_count}</b>\n\n"
    )
    detail = "\n".join(lines)
    full_text = summary + detail
    # Telegram message limit is 4096 chars
    if len(full_text) > 4000:
        full_text = summary + detail[:3800] + "\n…(truncated)"
    await status_msg.edit_text(full_text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /blockuser and /unbanuser commands — Owner only
# ---------------------------------------------------------------------------

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import time as _time

    start = _time.monotonic()

    # 1. Telegram handler processing time (time since message was sent by user)
    sent_at = update.message.date.timestamp()
    handler_ms = int((_time.monotonic() - (sent_at - _time.time() + _time.monotonic())) * 1000)
    # Simpler: just measure round-trip from now
    t0 = _time.monotonic()

    # 2. DB ping
    db_ms = -1
    if media_cache_col is not None:
        try:
            t_db = _time.monotonic()
            await media_cache_col.database.command("ping")
            db_ms = int((_time.monotonic() - t_db) * 1000)
        except Exception:
            db_ms = -1

    # 3. Network ping (hit Telegram API status page, a fast reliable endpoint)
    net_ms = -1
    try:
        t_net = _time.monotonic()
        req = urllib.request.Request(
            "https://api.telegram.org",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=5).read(128))
        net_ms = int((_time.monotonic() - t_net) * 1000)
    except Exception:
        net_ms = -1

    # Handler processing time = total time to run this handler
    handler_ms = int((_time.monotonic() - start) * 1000)

    db_str  = f"{db_ms} ms" if db_ms  >= 0 else "❌ unreachable"
    net_str = f"{net_ms} ms" if net_ms >= 0 else "❌ unreachable"

    text = (
        "🏓 <b>PONG!</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"⚡ <b>Handler Processing:</b> <code>{handler_ms} ms</code>\n"
        f"🗄 <b>Database Response:</b> <code>{db_str}</code>\n"
        f"🌐 <b>Network Response:</b> <code>{net_str}</code>\n"
        "━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def blockuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if banned_users_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    target_user, target_username = get_user_from_mention(update)
    if not target_user and target_username and users_col is not None:
        db_user = await users_col.find_one({"username": target_username})
        if db_user:
            class _DU:
                def __init__(self, uid, fname, uname):
                    self.id = uid; self.first_name = fname; self.username = uname; self.is_bot = False
            target_user = _DU(db_user["user_id"], db_user["first_name"], db_user["username"])

    if not target_user:
        await update.message.reply_text("❌ Please reply to a user's message or tag their @username properly!")
        return
    if target_user.id in OWNER_IDS:
        await update.message.reply_text("❌ You cannot ban an owner!")
        return

    await banned_users_col.update_one(
        {"user_id": target_user.id},
        {"$set": {"user_id": target_user.id, "name": target_user.first_name, "banned_by": update.effective_user.id}},
        upsert=True,
    )
    await update.message.reply_text(
        f"🚫 <b>{target_user.first_name}</b> has been banned from using the bot!",
        parse_mode="HTML",
    )


async def unbanuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if banned_users_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    target_user, target_username = get_user_from_mention(update)
    if not target_user and target_username and users_col is not None:
        db_user = await users_col.find_one({"username": target_username})
        if db_user:
            class _DU:
                def __init__(self, uid, fname, uname):
                    self.id = uid; self.first_name = fname; self.username = uname; self.is_bot = False
            target_user = _DU(db_user["user_id"], db_user["first_name"], db_user["username"])

    if not target_user:
        await update.message.reply_text("❌ Please reply to a user's message or tag their @username properly!")
        return

    result = await banned_users_col.delete_one({"user_id": target_user.id})
    if result.deleted_count:
        await update.message.reply_text(
            f"✅ <b>{target_user.first_name}</b> has been unbanned!",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(f"⚠️ {target_user.first_name} was not in the ban list.")


# ---------------------------------------------------------------------------
# /resetweekly command — Owner only: reset all weekly stats to 0
# ---------------------------------------------------------------------------

async def resetweekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if update.effective_user is None or update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if users_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return
    try:
        result = await users_col.update_many({}, {"$set": {
            "weekly_runs":        0,
            "weekly_wickets":     0,
            "weekly_conceded":    0,
            "weekly_balls_bowled": 0,
            "weekly_balls_faced":  0,
        }})
        await update.message.reply_text(
            f"✅ <b>Weekly leaderboard has been reset!</b>\n\n"
            f"📊 {result.modified_count} player records zeroed out.\n"
            f"🏏 Fresh week starts NOW! 🔄",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Reset failed: {e}")


# ---------------------------------------------------------------------------
# /ownerhelp command — Owner only: list all owner-only commands
# ---------------------------------------------------------------------------

async def ownerhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if update.effective_user is None or update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    text = (
        "🔑 <b>OWNER COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📢 <b>Broadcast &amp; Messaging</b>\n"
        "  /broadcast — Send a message to all groups &amp; DMs\n"
        "  /forward — Forward a replied message to all chats\n\n"
        "🔒 <b>Ban Management</b>\n"
        "  /blockuser — Ban a user from all matches\n"
        "  /unbanuser — Unban a user\n"
        "  /banlist — View all currently banned users\n\n"
        "🔑 <b>Permissions</b>\n"
        "  /permit — Grant a user host permission (optional duration)\n"
        "  /rpermit — Revoke a user's host permission\n\n"
        "📊 <b>Stats &amp; Info</b>\n"
        "  /botstats — View bot-wide statistics\n"
        "  /botgroups — List all groups the bot is in\n"
        "  /info [group_id] — View info on a specific group\n\n"
        "🏏 <b>Match Controls</b>\n"
        "  /penalty [Team] [Balls] [Runs] — Apply a penalty in a TEAM match\n\n"
        "🔄 <b>Leaderboard</b>\n"
        "  /resetweekly — Reset weekly leaderboard stats to 0 for all players\n\n"
        "🎪 <b>Tournament</b>\n"
        "  /tournament — Manage tournaments\n"
        "  /regisopen — Open team registration\n"
        "  /regisclose — Close team registration\n"
        "  /allteams — View all registered teams\n"
        "  /deleteteam — Delete a registered team\n\n"
        "🛠️ <b>Bot Utilities</b>\n"
        "  /cachemedia — Cache all bot media files\n"
        "  /ping — Check bot latency\n"
        "  /ownerhelp — Show this list\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /banlist command — Owner only: show all banned users
# ---------------------------------------------------------------------------

async def banlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if update.effective_user is None or update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("❌ Owner only command.")
        return
    if banned_users_col is None:
        await update.message.reply_text("❌ Database not connected.")
        return

    try:
        docs = await asyncio.wait_for(
            banned_users_col.find({}).to_list(length=500), timeout=10.0
        )
    except Exception:
        await update.message.reply_text("❌ Failed to fetch ban list. Try again.")
        return

    if not docs:
        await update.message.reply_text("✅ Ban list is currently empty. No users are banned.")
        return

    lines = ["🚫 <b>BANNED USERS LIST</b>\n"]
    for i, doc in enumerate(docs, 1):
        uid  = doc.get("user_id", "?")
        name = doc.get("name", "Unknown")
        lines.append(f"{i}. <a href='tg://user?id={uid}'>{name}</a> — <code>{uid}</code>")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n…(truncated)"
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /shift command — Team game host only: move player between teams
# ---------------------------------------------------------------------------

async def shift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return
    game = context.bot_data.get(chat_id)
    if not game or game.get("mode") != "TEAM":
        await update.message.reply_text("❌ No active team match found!")
        return
    if update.effective_user.id != game.get("host_id"):
        await update.message.reply_text("❌ Only the Host can use /shift!")
        return
    if game.get("state") not in ["PLAYING", "TEAM_JOINING"]:
        await update.message.reply_text("❌ /shift can only be used during an active match setup or game!")
        return

    target_user, target_username = get_user_from_mention(update)
    if not target_user and not target_username:
        await update.message.reply_text("❌ Please reply to a user's message or tag their @username!")
        return

    # Find the player in team_a or team_b
    found_team   = None
    found_player = None
    for team_key in ["team_a", "team_b"]:
        for p in game.get(team_key, {}).get("players", []):
            match_id   = target_user and p["id"] == target_user.id
            match_name = target_username and p.get("username") == target_username
            if match_id or match_name:
                found_team   = team_key
                found_player = p
                break
        if found_team:
            break

    if not found_player:
        name_str = target_user.first_name if target_user else target_username
        await update.message.reply_text(f"❌ {name_str} is not in any team!")
        return

    # Cannot shift current batter (striker / non-striker)
    striker     = game.get("striker") or {}
    non_striker = game.get("non_striker") or {}
    if found_player["id"] in (striker.get("id"), non_striker.get("id")):
        await update.message.reply_text(
            f"❌ Cannot shift <b>{found_player['name']}</b> — they are currently batting on the pitch!",
            parse_mode="HTML",
        )
        return

    # Cannot shift current bowler
    current_bowler = game.get("current_bowler") or {}
    if found_player["id"] == current_bowler.get("id"):
        await update.message.reply_text(
            f"❌ Cannot shift <b>{found_player['name']}</b> — they are currently bowling!",
            parse_mode="HTML",
        )
        return

    # Move player to the other team
    other_team_key = "team_b" if found_team == "team_a" else "team_a"
    game[found_team]["players"].remove(found_player)

    # Reassign numbers in original team
    for i, p in enumerate(game[found_team]["players"], 1):
        p["num"] = i

    # Reset player stats and assign new number
    found_player["num"] = len(game[other_team_key]["players"]) + 1
    found_player["is_out"] = False
    found_player["runs"] = 0
    found_player["balls_faced"] = 0
    found_player["wickets"] = 0
    found_player["conceded"] = 0
    found_player["balls_bowled"] = 0
    found_player["match_4s"] = 0
    found_player["match_6s"] = 0
    game[other_team_key]["players"].append(found_player)

    from_name = "Team A 🔴" if found_team == "team_a" else "Team B 🔵"
    to_name   = "Team B 🔵" if found_team == "team_a" else "Team A 🔴"
    await update.message.reply_text(
        f"🔄 <b>{found_player['name']}</b> has been shifted from {from_name} to {to_name}!",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Registration photo input handler
# ---------------------------------------------------------------------------

async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if context.user_data.get("reg_state") != "logo":
        return
    photo = update.message.photo[-1]
    context.user_data["reg_data"]["logo_file_id"] = photo.file_id
    context.user_data["reg_state"] = "captain"
    await update.message.reply_text(
        "✅ Logo received!\n\nStep 4️⃣\n👑 Send the <b>Captain's @username</b>.\n"
        "(If no username, send their full name)",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting ELITE CRICKET BOT Server...")
    print(f"Pillow available: {PIL_AVAILABLE}")

    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(TypeHandler(Update, global_tracker), group=-1)
    app.add_handler(ChatMemberHandler(track_bot_kicks, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CommandHandler("start",       start_command))
    app.add_handler(CommandHandler("join",        join_command))
    app.add_handler(CommandHandler("add",         add_command))
    app.add_handler(CommandHandler("remove",      remove_command))
    app.add_handler(CommandHandler("changehost",  changehost_command))
    app.add_handler(CommandHandler("changecap",   changecap_command))
    app.add_handler(CommandHandler("changeover",  changeover_command))
    app.add_handler(CommandHandler("create_team", create_team_command))
    app.add_handler(CommandHandler("rejoin",      rejoin_command))
    app.add_handler(CommandHandler("leavesolo",   leavesolo_command))
    app.add_handler(CommandHandler("startsolo",   startsolo_command))
    app.add_handler(CommandHandler("endmatch",    endmatch_command))
    app.add_handler(CommandHandler("soloscore",   soloscore_command))
    app.add_handler(CommandHandler("score",       teamscore_command))
    app.add_handler(CommandHandler("teams",       teams_command))
    app.add_handler(CommandHandler("batting",     batting_command))
    app.add_handler(CommandHandler("bowling",     bowling_command))
    app.add_handler(CommandHandler("userstats",   userstats_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("broadcast",   broadcast_command))
    app.add_handler(CommandHandler("forward",     forward_command))
    app.add_handler(CommandHandler("permit",      permit_command))
    app.add_handler(CommandHandler("rpermit",     rpermit_command))
    app.add_handler(CommandHandler("botstats",    botstats_command))
    app.add_handler(CommandHandler("delstats",    delstats_command))
    app.add_handler(CommandHandler("botgroups",   botgroups_command))
    app.add_handler(CommandHandler("info",        groupinfo_command))
    app.add_handler(CommandHandler("history",     history_command))
    app.add_handler(CommandHandler("spamfree",    spamfree_command))
    app.add_handler(CommandHandler("penalty",     penalty_command))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("ranking",      ranking_command))
    app.add_handler(CommandHandler("tournament",  tournament_command))
    app.add_handler(CommandHandler("regisopen",   regisopen_command))
    app.add_handler(CommandHandler("regisclose",  regisclose_command))
    app.add_handler(CommandHandler("register",    register_command))
    app.add_handler(CommandHandler("tourteams",   tourteams_command))
    app.add_handler(CommandHandler("allteams",    allteams_command))
    app.add_handler(CommandHandler("deleteteam",  deleteteam_command))
    app.add_handler(CommandHandler("cachemedia",  cachemedia_command))
    app.add_handler(CommandHandler("ping",        ping_command))
    app.add_handler(CommandHandler("blockuser",   blockuser_command))
    app.add_handler(CommandHandler("unbanuser",   unbanuser_command))
    app.add_handler(CommandHandler("banlist",     banlist_command))
    app.add_handler(CommandHandler("shift",       shift_command))
    app.add_handler(CommandHandler("resetweekly", resetweekly_command))
    app.add_handler(CommandHandler("ownerhelp",   ownerhelp_command))

    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.rstrip("/")
        print(f"Starting Webhook on Port {PORT}...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{clean_url}/{TOKEN}",
        )
    else:
        print("WEBHOOK_URL not found. Falling back to Polling...")
        app.run_polling(poll_interval=0.01, timeout=10, drop_pending_updates=True)
