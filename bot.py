# -*- coding: utf-8 -*-
import os, re, json, asyncio
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

# ========= НАСТРОЙКИ =========
TOKEN = os.getenv("BOT_TOKEN", "").strip()
YOUR_USERNAME = os.getenv("YOUR_USERNAME", "vadimpobedniy")
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@Protagonistofgame"
SONG_URL = "https://youtu.be/-orqHfJdo3E?si=7sCs_q7KTyd0rD8i"

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения Railway.")

# Файл для сохранения состояния (переживает рестарт процесса)
STATE_FILE = os.getenv("STATE_FILE", "state.json")

# ========= УРОКИ =========
LESSONS = {
    1: {
        "title": "Урок 1: Цена тени",
        "youtube": "https://youtu.be/ssLtF2UIVVc",
        "video": None,                 # на Railway видео обычно не кладём
        "auto_file": None,
        "links": [
            ("🧭 Получить разбор (Evolution)", "https://evolution.life/p/vadimpobedniy/products"),
            ("ℹ️ Что такое Evolution? (видео)", "https://youtu.be/jjq8STmDlf4?si=EQ9imb8Pw2lE9FTB"),
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
    },
    2: {
        "title": "Урок 2: Обнуляем страх",
        "youtube": "https://youtu.be/wRysU2M19vI",
        "video": None,
        "auto_file": "podcast_30_questions.pdf",   # положите файл в репо
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
    },
    3: {
        "title": "Урок 3: Говори так, чтобы тебя слушали",
        "youtube": "https://youtu.be/zc5NLQ3y_68",
        "video": None,
        "auto_file": None,
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
    },
    4: {
        "title": "Урок 4: Выход в эфир = рост возможностей",
        "youtube": "https://youtu.be/YoNxh203KCE",
        "video": None,
        "auto_file": "open any door.pdf",          # положите файл в репо
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
            ("🎵 «Маленькие шаги»", SONG_URL),
            ("📺 Подписаться на YouTube «Главный Герой»", YOUTUBE_CHANNEL_URL),
        ],
        "final_note": (
            "Благодарю за то, что был со мной эти четыре дня. Я верю в твой успех. "
            "Начинай записывать видео — и у тебя всё обязательно получится.\n\n"
            "Открыт к предложениям по совместным эфирам, подкастам и другим взаимодействиям. Я на связи."
        ),
    },
}

# ========= ПРОСТАЯ ПЕРСИСТЕНТНОСТЬ =========
# Структура: { "<chat_id>": {"step": int, "last": "ISO8601"} }
USERS: Dict[str, Dict[str, Any]] = {}

def load_state():
    global USERS
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Восстанавливаем datetime
            for k, v in raw.items():
                dt = v.get("last")
                v["last"] = datetime.fromisoformat(dt) if dt else datetime.min
            USERS = raw
        else:
            USERS = {}
    except Exception as e:
        print(f"[WARN] Не удалось загрузить {STATE_FILE}: {e}")
        USERS = {}

def save_state():
    try:
        out = {}
        for k, v in USERS.items():
            out[k] = {"step": v.get("step", 1), "last": v.get("last", datetime.min).isoformat()}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Не удалось сохранить {STATE_FILE}: {e}")

# ========= ВСПОМОГАТЕЛЬНЫЕ =========
def _kb_for_lesson(n: int) -> InlineKeyboardMarkup | None:
    meta = LESSONS[n]
    rows = []
    yt = meta.get("youtube")
    if yt:
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=yt)])
    vid = meta.get("video")
    if vid and os.path.exists(vid):
        rows.append([InlineKeyboardButton("⬇️ Скачать видео (MP4)", callback_data=f"dl_video_{n}")])
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None

async def send_lesson_package(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int):
    meta = LESSONS[n]
    title = meta["title"]

    # 1) Сообщение + все бонусные кнопки сразу
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {title}\n\nВыбирай, как удобнее смотреть: YouTube или скачать видео. Бонусы ниже ⤵️",
        reply_markup=_kb_for_lesson(n)
    )

    # 2) Автодокумент (если есть и найден)
    auto_file = meta.get("auto_file")
    if auto_file:
        if os.path.exists(auto_file):
            try:
                with open(auto_file, "rb") as f:
                    await context.bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(auto_file))
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить файл: {auto_file}\n{e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Файл не найден: {auto_file}")

    # 3) Финальная подпись только у урока 4
    if n == 4 and meta.get("final_note"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Связаться с Вадимом", url=f"https://t.me/{YOUR_USERNAME}")],
            [InlineKeyboardButton("🎵 «Маленькие шаги»", url=SONG_URL)],
            [InlineKeyboardButton("📺 Подписаться на YouTube «Главный Герой»", url=YOUTUBE_CHANNEL_URL)],
        ])
        await context.bot.send_message(chat_id=chat_id, text=meta["final_note"], reply_markup=kb)

# ========= ХЕНДЛЕРЫ =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    # Если пользователя нет — регистрируем и выдаём урок 1
    if chat_id not in USERS:
        USERS[chat_id] = {"step": 1, "last": datetime.now()}
        save_state()
        await update.message.reply_text("🚀 Стартуем. Твой первый урок готов 👇")
        await send_lesson_package(context, int(chat_id), 1)
    else:
        # Уже есть: повторно шлём текущий урок с кнопками
        cur = USERS[chat_id]["step"]
        await update.message.reply_text("Мы уже начали. Твой текущий урок 👇")
        await send_lesson_package(context, int(chat_id), cur)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "").strip()
    chat_id = str(q.message.chat.id)

    m = re.match(r"dl_video_(\d+)$", data)
    if m:
        n = int(m.group(1))
        path = LESSONS.get(n, {}).get("video")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=int(chat_id),
                        document=f,
                        filename=os.path.basename(path),
                        caption=LESSONS[n]["title"]
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=int(chat_id), text=f"Не удалось отправить видео: {e}")
        else:
            await context.bot.send_message(chat_id=int(chat_id), text="Видео пока недоступно.")
        return

# Доп. команда на всякий случай: вручную выдать следующий урок
async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in USERS:
        USERS[chat_id] = {"step": 0, "last": datetime.now() - timedelta(days=2)}
    cur = USERS[chat_id]["step"]
    if cur >= 4:
        await update.message.reply_text("Все 4 урока уже выданы 🎉")
        return
    USERS[chat_id]["step"] = cur + 1
    USERS[chat_id]["last"] = datetime.now()
    save_state()
    await send_lesson_package(context, int(chat_id), USERS[chat_id]["step"])

# ========= JOBQUEUE: проверка каждые 60 сек =========
async def check_and_send(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    # копия ключей, чтобы не сломаться при модификации
    for chat_id in list(USERS.keys()):
        st = USERS.get(chat_id) or {}
        step = st.get("step", 1)
        last = st.get("last", datetime.min)
        if step < 4 and now - last >= timedelta(days=1):
            USERS[chat_id]["step"] = step + 1
            USERS[chat_id]["last"] = now
            save_state()
            await send_lesson_package(context, int(chat_id), USERS[chat_id]["step"])

# ========= ЗАПУСК =========
def main():
    load_state()
    app: Application = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_cmd))  # ручной пропуск вперёд
    app.add_handler(CallbackQueryHandler(on_callback))

    # Планировщик PTB (надежно): шлём проверку каждые 60 сек
    app.job_queue.run_repeating(check_and_send, interval=60, first=10)

    print("Бот запущен… (боевой режим: 1 урок/сутки; JobQueue + state.json)")
    app.run_polling()

if __name__ == "__main__":
    main()
