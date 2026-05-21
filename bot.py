import logging
import sqlite3
import os
from datetime import datetime
from collections import Counter

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ============================================================
#  ⚙️  Railway Variables-এ BOT_TOKEN বসান
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_FILE = "members.db"


# ─────────────────────────────────────────
# ডেটাবেজ সেটআপ
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id       INTEGER PRIMARY KEY,
            first_name    TEXT,
            last_name     TEXT,
            username      TEXT,
            bio           TEXT,
            is_premium    INTEGER DEFAULT 0,
            is_bot        INTEGER DEFAULT 0,
            language_code TEXT,
            first_seen    TEXT,
            last_seen     TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            chat_id      INTEGER,
            message_type TEXT,
            hour         INTEGER,
            created_at   TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS name_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            old_name   TEXT,
            new_name   TEXT,
            changed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS username_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER,
            old_username   TEXT,
            new_username   TEXT,
            changed_at     TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            reason     TEXT,
            warned_by  INTEGER,
            warned_at  TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# মেম্বার সেভ / আপডেট
# ─────────────────────────────────────────
def save_member(user):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = c.execute(
        "SELECT first_name, username FROM members WHERE user_id = ?",
        (user.id,)
    ).fetchone()

    full_name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")

    if existing:
        old_name = existing[0]
        old_username = existing[1]

        if old_name and old_name.strip() != full_name.strip():
            c.execute(
                "INSERT INTO name_history (user_id, old_name, new_name, changed_at) VALUES (?, ?, ?, ?)",
                (user.id, old_name, full_name, now)
            )

        if old_username != user.username:
            c.execute(
                "INSERT INTO username_history (user_id, old_username, new_username, changed_at) VALUES (?, ?, ?, ?)",
                (user.id, old_username, user.username, now)
            )

        c.execute("""
            UPDATE members SET
                first_name = ?, last_name = ?, username = ?,
                is_premium = ?, is_bot = ?, language_code = ?, last_seen = ?
            WHERE user_id = ?
        """, (
            user.first_name, user.last_name, user.username,
            1 if getattr(user, "is_premium", False) else 0,
            1 if user.is_bot else 0,
            user.language_code, now, user.id
        ))
    else:
        c.execute("""
            INSERT INTO members
                (user_id, first_name, last_name, username, is_premium, is_bot, language_code, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id,
            user.first_name, user.last_name, user.username,
            1 if getattr(user, "is_premium", False) else 0,
            1 if user.is_bot else 0,
            user.language_code, now, now
        ))

    conn.commit()
    conn.close()


def save_message(user_id, chat_id, message_type, hour):
    conn = sqlite3.connect(DB_FILE)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO messages (user_id, chat_id, message_type, hour, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, chat_id, message_type, hour, now)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# মেসেজের ধরন বের করা
# ─────────────────────────────────────────
def get_message_type(message):
    if message.photo:       return "photo"
    if message.video:       return "video"
    if message.audio:       return "audio"
    if message.voice:       return "voice"
    if message.document:    return "document"
    if message.sticker:     return "sticker"
    if message.animation:   return "animation"
    if message.video_note:  return "video_note"
    return "text"


# ─────────────────────────────────────────
# সবচেয়ে বেশি অ্যাক্টিভ সময়
# ─────────────────────────────────────────
def get_active_time(user_id):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT hour FROM messages WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return "তথ্য নেই"

    hours = [r[0] for r in rows]
    counter = Counter(hours)
    peak_hour = counter.most_common(1)[0][0]

    if 5 <= peak_hour < 12:   return f"সকাল ({peak_hour}:00)"
    if 12 <= peak_hour < 17:  return f"দুপুর ({peak_hour}:00)"
    if 17 <= peak_hour < 21:  return f"বিকাল ({peak_hour}:00)"
    return f"রাত ({peak_hour}:00)"


# ─────────────────────────────────────────
# ইতিহাস বের করা
# ─────────────────────────────────────────
def get_name_history(user_id):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT old_name, new_name FROM name_history WHERE user_id = ? ORDER BY changed_at",
        (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_username_history(user_id):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT old_username, new_username FROM username_history WHERE user_id = ? ORDER BY changed_at",
        (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_warning_count(user_id):
    conn = sqlite3.connect(DB_FILE)
    count = conn.execute(
        "SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


# ─────────────────────────────────────────
# মেম্বার ইনফো কার্ড তৈরি
# ─────────────────────────────────────────
def build_info_text(member_data, msg_stats, active_time, name_hist, uname_hist, warn_count, is_admin):
    user_id, first_name, last_name, username, bio, is_premium, is_bot, lang, first_seen, last_seen = member_data

    full_name = first_name or ""
    if last_name:
        full_name += f" {last_name}"

    uname_str = f"@{username}" if username else "নেই"
    bio_str   = bio if bio else "নেই"
    lang_str  = lang if lang else "অজানা"

    premium_str = "⭐ হ্যাঁ" if is_premium else "না"
    bot_str     = "🤖 হ্যাঁ" if is_bot     else "না"
    admin_str   = "👑 হ্যাঁ" if is_admin   else "না"

    total  = msg_stats.get("total", 0)
    texts  = msg_stats.get("text", 0)
    photos = msg_stats.get("photo", 0)
    videos = msg_stats.get("video", 0)
    others = total - texts - photos - videos

    def fmt(dt_str):
        if not dt_str:
            return "তথ্য নেই"
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d %B %Y, %I:%M %p")
        except:
            return dt_str

    if name_hist:
        names = [name_hist[0][0]] + [r[1] for r in name_hist]
        name_hist_str = " → ".join(names)
    else:
        name_hist_str = "কোনো পরিবর্তন নেই"

    if uname_hist:
        unames = []
        for r in uname_hist:
            if r[0]: unames.append(f"@{r[0]}")
        if uname_hist[-1][1]:
            unames.append(f"@{uname_hist[-1][1]}")
        uname_hist_str = " → ".join(unames) if unames else "কোনো পরিবর্তন নেই"
    else:
        uname_hist_str = "কোনো পরিবর্তন নেই"

    text = (
        f"╔══════════════════════╗\n"
        f"       📋 মেম্বার তথ্য\n"
        f"╚══════════════════════╝\n\n"
        f"👤 নাম: {full_name}\n"
        f"🔖 ইউজারনেম: {uname_str}\n"
        f"🆔 Telegram ID: `{user_id}`\n"
        f"📝 Bio: {bio_str}\n"
        f"🌐 ভাষা: {lang_str}\n"
        f"⭐ Premium: {premium_str}\n"
        f"🤖 Bot: {bot_str}\n"
        f"👑 Admin: {admin_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 মেসেজ পরিসংখ্যান\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 মোট মেসেজ: {total}টি\n"
        f"   ✏️ টেক্সট: {texts}টি\n"
        f"   🖼️ ছবি: {photos}টি\n"
        f"   🎬 ভিডিও: {videos}টি\n"
        f"   📎 অন্যান্য: {others}টি\n\n"
        f"📅 প্রথম মেসেজ: {fmt(first_seen)}\n"
        f"⏰ শেষ মেসেজ: {fmt(last_seen)}\n"
        f"🕐 বেশি অ্যাক্টিভ: {active_time}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📜 পরিবর্তনের ইতিহাস\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✏️ নাম ইতিহাস:\n{name_hist_str}\n\n"
        f"🔄 ইউজারনেম ইতিহাস:\n{uname_hist_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Warning: {warn_count}টি\n"
    )
    return text


# ─────────────────────────────────────────
# মেসেজ হ্যান্ডলার — সব মেসেজ ট্র্যাক
# ─────────────────────────────────────────
async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    save_member(user)

    msg_type = get_message_type(update.message)
    hour = datetime.now().hour
    save_message(user.id, update.message.chat_id, msg_type, hour)

    entities = update.message.entities or []
    mentioned_users = []

    for entity in entities:
        if entity.type == "mention":
            uname = update.message.text[entity.offset + 1: entity.offset + entity.length]
            mentioned_users.append(("username", uname))
        elif entity.type == "text_mention" and entity.user:
            mentioned_users.append(("user", entity.user))

    bot_username = context.bot.username
    bot_mentioned = any(
        (t == "username" and v.lower() == bot_username.lower())
        for t, v in mentioned_users
    )

    if not bot_mentioned:
        return

    # বট ছাড়া অন্য mention = টার্গেট ইউজার
    target_row = None
    for t, v in mentioned_users:
        if t == "username" and v.lower() != bot_username.lower():
            conn = sqlite3.connect(DB_FILE)
            row = conn.execute(
                "SELECT * FROM members WHERE LOWER(username) = LOWER(?)", (v,)
            ).fetchone()
            conn.close()
            if row:
                target_row = row
                break
            else:
                await update.message.reply_text(
                    f"⚠️ @{v} এর তথ্য পাওয়া যায়নি।\n"
                    f"কারণ: তিনি এখনো গ্রুপে কোনো মেসেজ পাঠাননি।"
                )
                return
        elif t == "user":
            save_member(v)
            conn = sqlite3.connect(DB_FILE)
            target_row = conn.execute(
                "SELECT * FROM members WHERE user_id = ?", (v.id,)
            ).fetchone()
            conn.close()
            break

    if not target_row:
        return

    user_id = target_row[0]

    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT message_type FROM messages WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()

    msg_stats = {"total": len(rows)}
    for (mtype,) in rows:
        msg_stats[mtype] = msg_stats.get(mtype, 0) + 1

    is_admin = False
    target_row = list(target_row)
    try:
        member = await context.bot.get_chat_member(update.message.chat_id, user_id)
        is_admin = member.status in ("administrator", "creator")

        chat = await context.bot.get_chat(user_id)
        if chat.bio:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE members SET bio = ? WHERE user_id = ?", (chat.bio, user_id))
            conn.commit()
            conn.close()
            target_row[4] = chat.bio
    except Exception as e:
        logger.warning(f"Admin/Bio fetch error: {e}")

    target_row = tuple(target_row)

    active_time = get_active_time(user_id)
    name_hist   = get_name_history(user_id)
    uname_hist  = get_username_history(user_id)
    warn_count  = get_warning_count(user_id)

    info_text = build_info_text(
        target_row, msg_stats,
        active_time, name_hist, uname_hist,
        warn_count, is_admin
    )

    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            photo = photos.photos[0][0]
            await update.message.reply_photo(
                photo=photo.file_id,
                caption=info_text,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(info_text, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Photo error: {e}")
        await update.message.reply_text(info_text, parse_mode="Markdown")


# ─────────────────────────────────────────
# /warn কমান্ড
# ─────────────────────────────────────────
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কাউকে reply করে /warn দিন।")
        return

    caller = await context.bot.get_chat_member(
        update.message.chat_id, update.message.from_user.id
    )
    if caller.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ শুধু Admin warn দিতে পারবেন।")
        return

    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "কারণ উল্লেখ নেই"

    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO warnings (user_id, reason, warned_by, warned_at) VALUES (?, ?, ?, ?)",
        (target.id, reason, update.message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM warnings WHERE user_id = ?", (target.id,)
    ).fetchone()[0]
    conn.close()

    name = target.first_name or "ইউজার"
    await update.message.reply_text(
        f"⚠️ {name} কে Warning দেওয়া হয়েছে!\n"
        f"কারণ: {reason}\n"
        f"মোট Warning: {count}টি"
    )


# ─────────────────────────────────────────
# /top কমান্ড
# ─────────────────────────────────────────
async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT m.user_id, m.first_name, m.username, COUNT(msg.id) as cnt
        FROM members m
        LEFT JOIN messages msg ON m.user_id = msg.user_id
        GROUP BY m.user_id
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("এখনো কোনো ডেটা নেই।")
        return

    text = "🏆 সবচেয়ে অ্যাক্টিভ মেম্বার:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, fname, uname, cnt) in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = fname or "Unknown"
        text += f"{medal} {name} — {cnt}টি মেসেজ\n"

    await update.message.reply_text(text)


# ─────────────────────────────────────────
# /start এবং /help
# ─────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 আমি Member Info Bot!\n\n"
        "📌 ব্যবহার:\n"
        "@botname @targetuser — মেম্বারের সকল তথ্য দেখুন\n\n"
        "📌 কমান্ড:\n"
        "/top — সবচেয়ে অ্যাক্টিভ মেম্বার\n"
        "/warn — কাউকে ওয়ার্নিং দিন (reply করে)\n"
        "/help — সাহায্য"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


# ─────────────────────────────────────────
# মেইন
# ─────────────────────────────────────────
def main():
    init_db()
    print("✅ ডেটাবেজ তৈরি হয়েছে।")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_message))

    print("🤖 বট চালু হয়েছে!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
