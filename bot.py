# -*- coding: utf-8 -*-
# bot.py — стабильная версия с JobQueue и кнопкой «Скачать материалы»
# Требуется: python-telegram-bot[job-queue]==20.7 (в requirements.txt)

import os, re, json, logging
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("bot")

# ===== НАСТРОЙКИ =====
TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "").strip()
YOUR_USERNAME = os.getenv("YOUR_USERNAME", "vadimpobedniy")

YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@Protagonistofgame"
SONG_URL = "https://youtu.be/-orqHfJdo3E?si=7sCs_q7KTyd0rD8i"
STATE_FILE = "/tmp/state.json"  # Railway: сюда точно можно писать

if not TOKEN:
    log.error("Не задан BOT_TOKEN в Railway → Variables.")
    raise SystemExit(1)

# ===== УРОКИ =====
# В auto_file укажи точное имя файла (с учётом регистра и пробелов),
# файл должен лежать рядом с bot.py в репозитории.
LESSONS = {
    1: {
        "title": "Урок 1: Цена тени",
        "youtube": "https://youtu.be/ssLtF2UIVVc",
        "video": None,
        "auto_file": None,  # например: "lesson1_bonus.pdf" если будет
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
        "auto_file": "podcast_30_questions.pdf",
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
    },
    3: {
        "title": "Урок 3: Говори так, чтобы тебя слушали",
        "youtube": "https://youtu.be/zc5NLQ3y_68",
        "video": None,
        "auto_file": None,  # например: "lesson3_practice.pdf" если будет
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
    },
    4: {
        "title": "Урок 4: Выход в эфир = рост возможностей",
        "youtube": "https://youtu.be/YoNxh203KCE",
        "video": None,
        "auto_file": "open any door.pdf",
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

# ===== ПРОГРЕСС ПОЛЬЗОВАТЕЛЕЙ =====
USERS: Dict[str, Dict[str, Any]] = {}

def load_state():
    global USERS
    try:
        if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                s = v.get("last")
                v["last"] = datetime.fromisoformat(s) if isinstance(s, str) else datetime.min
            USERS = data
            log.info(f"Загружено пользователей: {len(USERS)}")
        else:
            USERS = {}
            log.info("STATE не найден или пуст — начнем с нуля")
    except Exception as e:
        log.warning(f"Не удалось загрузить состояние: {e}")
        USERS = {}

def save_state():
    try:
        out = {k: {"step": v.get("step", 1), "last": v.get("last", datetime.min).isoformat()} for k, v in USERS.items()}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Не удалось сохранить состояние: {e}")

# ===== КНОПКИ И ОТПРАВКА =====
def kb_for_lesson(n: int) -> InlineKeyboardMarkup | None:
    meta = LESSONS[n]
    rows = []
    if meta.get("youtube"):
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=meta["youtube"])])
    # Кнопка «Скачать материалы» показываем, если В КОДЕ указан auto_file (не проверяем наличие)
    if meta.get("auto_file"):
        rows.append([InlineKeyboardButton("📎 Скачать материалы", callback_data=f"dl_doc_{n}")])
    # Кнопка «Скачать видео (MP4)» — если когда-нибудь добавишь локальные видеофайлы
    vid = meta.get("video")
    if vid:
        rows.append([InlineKeyboardButton("⬇️ Скачать видео (MP4)", callback_data=f"dl_video_{n}")])
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None

async def send_lesson(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int):
    meta = LESSONS[n]
    # 1) Текст + кнопки (кнопка «Скачать материалы» уже тут)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {meta['title']}\n\nВыбирай, как удобнее смотреть: YouTube или скачать. Бонусы ниже ⤵️",
        reply_markup=kb_for_lesson(n)
    )
    # 2) Тут же пытаемся отправить файл (если указан) отдельным «бабблом» — это даст «Скачать» прямо в чате
    file_path = meta.get("auto_file")
    if file_path:
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=os.path.basename(file_path),
                        caption="Материалы к уроку"
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить файл: {file_path}\n{e}")
        else:
            # файл не нашли — всё равно кнопка есть, при нажатии ещё раз попробуем
            await context.bot.send_message(chat_id=chat_id, text=f"Пока не вижу файл: {file_path}. Проверь название в репозитории.")

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in USERS:
        USERS[chat_id] = {"step": 1, "last": datetime.now()}
        save_state()
        await update.message.reply_text("🚀 Стартуем. Твой первый урок готов 👇")
        await send_lesson(context, int(chat_id), 1)
    else:
        cur = USERS[chat_id]["step"]
        await update.message.reply_text("Мы уже начали. Твой текущий урок 👇")
        await send_lesson(context, int(chat_id), cur)

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
    await send_lesson(context, int(chat_id), USERS[chat_id]["step"])

# ===== ОБРАБОТКА КНОПОК «Скачать …» =====
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "").strip()
    chat_id = int(q.message.chat.id)

    # Скачать материалы (PDF/док)
    m = re.match(r"dl_doc_(\d+)$", data)
    if m:
        n = int(m.group(1))
        file_path = LESSONS.get(n, {}).get("auto_file")
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=os.path.basename(file_path),
                        caption="Материалы к уроку"
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить файл: {e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Материалы пока недоступны. Проверь имя файла в репозитории.")
        return

    # Скачать видео (если когда-нибудь добавишь локальные mp4)
    m = re.match(r"dl_video_(\d+)$", data)
    if m:
        n = int(m.group(1))
        path = LESSONS.get(n, {}).get("video")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=os.path.basename(path),
                        caption=LESSONS[n]["title"]
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить видео: {e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Видео пока недоступно.")

# ===== АВТО-ВЫДАЧА РАЗ В СУТКИ =====
async def tick(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for chat_id, st in list(USERS.items()):
        step, last = st.get("step", 1), st.get("last", datetime.min)
        if step < 4 and now - last >= timedelta(days=1):
            USERS[chat_id]["step"] = step + 1
            USERS[chat_id]["last"] = now
            save_state()
            await send_lesson(context, int(chat_id), USERS[chat_id]["step"])

# ===== ЗАПУСК =====
def main():
    log.info("Старт бота…")
    load_state()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    # Требуется пакет с job-queue (см. requirements.txt)
    if app.job_queue is None:
        log.error('JobQueue не создан. В requirements.txt должна быть строка: python-telegram-bot[job-queue]==20.7')
        raise SystemExit(1)

    app.job_queue.run_repeating(tick, interval=60, first=10)
    log.info("Бот запущен… (боевой режим: 1 урок/сутки)")
    app.run_polling()

if __name__ == "__main__":
    main()
