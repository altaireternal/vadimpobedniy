# -*- coding: utf-8 -*-
# Бот: YouTube + локальные видео/документы + авторассылка раз в 24 часа.
# Требуется: python-telegram-bot[job-queue]==20.7  (строка в requirements.txt)

import os, json, logging, re
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

if not TOKEN:
    log.error("Не задан BOT_TOKEN в Railway → Variables.")
    raise SystemExit(1)

STATE_FILE = "/tmp/state.json"   # прогресс пользователей
MEDIA_DIR  = os.getenv("MEDIA_DIR", "media")  # папка с файлами рядом с bot.py

def P(*parts):  # путь внутри MEDIA_DIR
    return os.path.join(MEDIA_DIR, *parts)

# ===== УРОКИ (подправь имена файлов под свои; размер видео <= 50 МБ) =====
LESSONS: Dict[int, Dict[str, Any]] = {
    1: {
        "title": "Урок 1: Цена тени",
        "youtube": "https://youtu.be/ssLtF2UIVVc",
        "video_path": P("lesson1.mp4"),                # mp4 16:9
        "docs": [],                                     # напр. [P("lesson1_bonus.pdf")]
        "links": [
            ("🧭 Получить разбор (Evolution)", "https://evolution.life/p/vadimpobedniy/products"),
            ("ℹ️ Что такое Evolution? (видео)", "https://youtu.be/jjq8STmDlf4?si=EQ9imb8Pw2lE9FTB"),
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
        "final_note": None,
    },
    2: {
        "title": "Урок 2: Обнуляем страх",
        "youtube": "https://youtu.be/wRysU2M19vI",
        "video_path": P("lesson2.mp4"),
        "docs": [P("podcast_30_questions.pdf")],
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
        "final_note": None,
    },
    3: {
        "title": "Урок 3: Говори так, чтобы тебя слушали",
        "youtube": "https://youtu.be/zc5NLQ3y_68",
        "video_path": P("lesson3.mp4"),
        "docs": [],  # напр. [P("lesson3_practice.pdf")]
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
        "final_note": None,
    },
    4: {
        "title": "Урок 4: Выход в эфир = рост возможностей",
        "youtube": "https://youtu.be/YoNxh203KCE",
        "video_path": P("lesson4.mp4"),
        "docs": [P("open any door.pdf")],
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
            ("🎵 «Маленькие шаги»", "https://youtu.be/-orqHfJdo3E?si=7sCs_q7KTyd0rD8i"),
            ("📺 Подписаться на YouTube «Главный Герой»", "https://www.youtube.com/@Protagonistofgame"),
        ],
        "final_note": (
            "Благодарю за то, что был со мной эти четыре дня. Я верю в твой успех. "
            "Начинай записывать видео — и у тебя всё обязательно получится.\n\n"
            "Открыт к предложениям по совместным эфирам, подкастам и другим взаимодействиям. Я на связи."
        ),
    },
}

# ===== ПРОГРЕСС =====
USERS: Dict[str, Dict[str, Any]] = {}

def load_state():
    global USERS
    try:
        if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            USERS = {}
            for cid, st in raw.items():
                last = st.get("last")
                USERS[cid] = {
                    "step": st.get("step", 1),
                    "last": datetime.fromisoformat(last) if last else datetime.min
                }
            log.info(f"Загружено пользователей: {len(USERS)}")
        else:
            USERS = {}
            log.info("STATE не найден или пуст — начнём с нуля")
    except Exception as e:
        log.warning(f"Не удалось загрузить состояние: {e}")
        USERS = {}

def save_state():
    out = {cid: {"step": st.get("step", 1), "last": st.get("last", datetime.min).isoformat()} for cid, st in USERS.items()}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Не удалось сохранить состояние: {e}")

# ===== КНОПКИ =====
def kb_for_lesson(n: int) -> InlineKeyboardMarkup:
    meta = LESSONS[n]
    rows = []
    if meta.get("youtube"):
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=meta["youtube"])])
    if meta.get("video_path"):
        rows.append([InlineKeyboardButton("📥 Скачать видео (MP4 без сжатия)", callback_data=f"dl_video_{n}")])
    if meta.get("docs"):
        rows.append([InlineKeyboardButton("📎 Скачать материалы (PDF)", callback_data=f"dl_docs_{n}")])
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None

# ===== ОТПРАВКА УРОКА =====
async def send_lesson(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int):
    meta = LESSONS[n]

    # Сообщение с заголовком + кнопки
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {meta['title']}\n\nСмотри на YouTube или скачай оригинал. Бонусы ниже ⤵️",
        reply_markup=kb_for_lesson(n)
    )

    # 1) Видео — как video (просмотр 16:9)
    vpath = meta.get("video_path")
    if vpath and os.path.exists(vpath):
        try:
            with open(vpath, "rb") as vf:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=vf,
                    caption=meta["title"],
                    supports_streaming=True
                )
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить видео: {e}")
    elif vpath:
        await context.bot.send_message(chat_id=chat_id, text=f"Видео не найдено на сервере: {vpath}")

    # 2) Бонусы — как документы (каждый отдельным сообщением)
    for dpath in meta.get("docs", []):
        if dpath and os.path.exists(dpath):
            try:
                with open(dpath, "rb") as df:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=df,
                        filename=os.path.basename(dpath),
                        caption="Материалы к уроку"
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить материалы: {e}")
        elif dpath:
            await context.bot.send_message(chat_id=chat_id, text=f"Материал не найден: {dpath}")

    # 3) Финальная подпись в 4-м уроке
    if n == 4 and meta.get("final_note"):
        await context.bot.send_message(chat_id=chat_id, text=meta["final_note"], reply_markup=kb_for_lesson(n))

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

# ===== ОБРАБОТКА КНОПОК СКАЧАТЬ =====
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "").strip()
    chat_id = int(q.message.chat.id)

    # Скачивание видео как document (без сжатия)
    m = re.match(r"dl_video_(\d+)$", data)
    if m:
        n = int(m.group(1))
        vpath = LESSONS.get(n, {}).get("video_path")
        if vpath and os.path.exists(vpath):
            try:
                with open(vpath, "rb") as vf:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=vf,
                        filename=os.path.basename(vpath),
                        caption="Скачай оригинальное видео (MP4)"
                    )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить видео: {e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Видео не найдено на сервере.")
        return

    # Скачивание всех материалов (PDF/док) по очереди
    m = re.match(r"dl_docs_(\d+)$", data)
    if m:
        n = int(m.group(1))
        docs = LESSONS.get(n, {}).get("docs") or []
        if not docs:
            await context.bot.send_message(chat_id=chat_id, text="Материалы отсутствуют.")
            return
        sent_any = False
        for dpath in docs:
            if dpath and os.path.exists(dpath):
                try:
                    with open(dpath, "rb") as df:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=df,
                            filename=os.path.basename(dpath),
                            caption="Материалы к уроку"
                        )
                    sent_any = True
                except Exception as e:
                    await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить: {os.path.basename(dpath)}\n{e}")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"Не найден: {dpath}")
        if not sent_any:
            await context.bot.send_message(chat_id=chat_id, text="Материалы сейчас недоступны.")

# ===== АВТО РАЗ В СУТКИ =====
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
    load_state()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    if app.job_queue is None:
        log.error('Нужен пакет: python-telegram-bot[job-queue]==20.7 в requirements.txt')
        raise SystemExit(1)
    app.job_queue.run_repeating(tick, interval=60, first=10)

    log.info("Бот запущен… (YouTube + локальные файлы, 1 урок/сутки)")
    app.run_polling()

if __name__ == "__main__":
    main()
