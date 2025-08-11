# -*- coding: utf-8 -*-
import os, re, asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ===== НАСТРОЙКИ =====
TOKEN = "8236283138:AAEjpYyGD9u6JXPcx-o1__ZY5yqkQvML-dU"   # твой токен
YOUR_USERNAME = "vadimpobedniy"                             # без @
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@Protagonistofgame"
SONG_URL = "https://youtu.be/-orqHfJdo3E?si=7sCs_q7KTyd0rD8i"

# ===== МАТЕРИАЛЫ ПО УРОКАМ =====
# video — локальный mp4 (если есть, отдадим «Скачать видео» как документ, чтобы не резало 16:9)
# auto_file — доп. документ (PDF и т.п.) — пришлём автоматически сразу после текста и кнопок
# links — кнопки-бонусы, которые всегда приходят сразу
LESSONS = {
    1: {
        "title": "Урок 1: Цена тени",
        "youtube": "https://youtu.be/ssLtF2UIVVc",
        "video": "lesson1.mp4",   # опционально: положи рядом с bot.py, иначе кнопка «Скачать» не покажется
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
        "video": "lesson2.mp4",
        "auto_file": "podcast_30_questions.pdf",  # PDF «30 вопросов»
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
    },
    3: {
        "title": "Урок 3: Говори так, чтобы тебя слушали",
        "youtube": "https://youtu.be/zc5NLQ3y_68",
        "video": "lesson3.mp4",
        "auto_file": None,
        "links": [
            ("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}"),
        ],
    },
    4: {
        "title": "Урок 4: Выход в эфир = рост возможностей",
        "youtube": "https://youtu.be/YoNxh203KCE",
        "video": "lesson4.mp4",
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

# Храним простое состояние в памяти процесса
USERS = {}  # chat_id -> {"step": int, "last": datetime}

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def build_keyboard_for_lesson(n: int) -> InlineKeyboardMarkup:
    meta = LESSONS[n]
    rows = []
    if meta.get("youtube"):
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=meta["youtube"])])
    # кнопка «Скачать видео» показывается только если файл реально есть на диске
    vid = meta.get("video")
    if vid and os.path.exists(vid):
        rows.append([InlineKeyboardButton("⬇️ Скачать видео (MP4)", callback_data=f"dl_video_{n}")])
    # бонусные ссылки — всегда
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None

async def send_lesson_package(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int):
    meta = LESSONS[n]
    title = meta["title"]

    # 1) Текст-объявление урока
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {title}\n\nВыбирай, как удобнее смотреть: YouTube или скачать видео. Бонусы ниже ⤵️",
        reply_markup=build_keyboard_for_lesson(n)
    )

    # 2) Авто-документ (если есть)
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

    # 3) Финальная подпись (только в уроке 4, если задана)
    if n == 4 and meta.get("final_note"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Связаться с Вадимом", url=f"https://t.me/{YOUR_USERNAME}")],
            [InlineKeyboardButton("🎵 «Маленькие шаги»", url=SONG_URL)],
            [InlineKeyboardButton("📺 Подписаться на YouTube «Главный Герой»", url=YOUTUBE_CHANNEL_URL)],
        ])
        await context.bot.send_message(chat_id=chat_id, text=meta["final_note"], reply_markup=kb)

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    USERS[chat_id] = {"step": 1, "last": datetime.now()}
    await update.message.reply_text("🚀 Стартуем. Твой первый урок готов 👇")
    await send_lesson_package(context, chat_id, 1)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = (q.data or "").strip()
    chat_id = q.message.chat.id

    m = re.match(r"dl_video_(\d+)$", data)
    if m:
        n = int(m.group(1))
        path = LESSONS.get(n, {}).get("video")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    # отправляем как документ, чтобы Telegram не резал 16:9 в квадрат
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
        return

# Планировщик: раз в сутки отдаём следующий урок
async def scheduler(app):
    while True:
        now = datetime.now()
        for chat_id, st in list(USERS.items()):
            step, last = st["step"], st["last"]
            if step < 4 and now - last >= timedelta(days=1):
                next_step = step + 1
                USERS[chat_id]["step"] = next_step
                USERS[chat_id]["last"] = now
                await send_lesson_package(app.bot, chat_id, next_step)
            elif step == 4:
                # всё выдали — можно удалять запись через сутки после 4-го (по желанию)
                pass
        await asyncio.sleep(60)  # опрос раз в минуту

# ===== ЗАПУСК =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    # фоновая задача планировщика
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler(app))
    print("Бот запущен… (боевой режим: 1 урок в сутки)")
    app.run_polling()

