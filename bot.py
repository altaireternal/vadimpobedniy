# -*- coding: utf-8 -*-
# Бот: YouTube + скачивание оригиналов по кнопкам (без авто-видео/превью).
# Авто-выдача следующего урока каждые 24 часа через JobQueue.
# Требуется: python-telegram-bot[job-queue]==20.7  (ровно эта строка в requirements.txt)

import os
import re
import csv
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("bot")

# ===== НАСТРОЙКИ =====
TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "").strip()
YOUR_USERNAME = os.getenv("YOUR_USERNAME", "vadimpobedniy")

# ПЕРСИСТЕНТНОЕ ХРАНИЛИЩЕ (Railway Volume монтируем в /app/data)
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, "state.json")
USERS_CSV  = os.path.join(DATA_DIR, "users.csv")

# Админы (кому доступны /users /stuck1 /stats /checkfiles /exportusers)
ADMIN_IDS = {"444338007"}  # добавь при необходимости ещё ID как строки

if not TOKEN:
    log.error("Не задан BOT_TOKEN в Railway → Variables.")
    raise SystemExit(1)

# Где ищем файлы с уроками: сперва в media/, затем в корне репо
SEARCH_DIRS: List[str] = ["media", "."]

def find_path(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    for base in SEARCH_DIRS:
        path = os.path.join(base, filename) if base != "." else filename
        if os.path.exists(path):
            return path
    return None

# ===== УРОКИ =====
LESSONS: Dict[int, Dict[str, Any]] = {
    1: {
        "title": "Урок 1: Цена тени",
        "youtube": "https://youtu.be/ssLtF2UIVVc",
        "video_file": "lesson1.mp4",
        "docs": [],
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
        "video_file": "lesson2.mp4",
        "docs": ["podcast_30_questions.pdf"],
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
        "final_note": None,
    },
    3: {
        "title": "Урок 3: Говори так, чтобы тебя слушали",
        "youtube": "https://youtu.be/zc5NLQ3y_68",
        "video_file": "lesson3.mp4",
        "docs": [],
        "links": [("📩 Связаться с Вадимом", f"https://t.me/{YOUR_USERNAME}")],
        "final_note": None,
    },
    4: {
        "title": "Урок 4: Выход в эфир = рост возможностей",
        "youtube": "https://youtu.be/YoNxh203KCE",
        "video_file": "lesson4.mp4",
        "docs": ["open any door.pdf"],   # проверь точное имя файла в репо
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

# ===== ПРОГРЕСС ПОЛЬЗОВАТЕЛЕЙ =====
USERS: Dict[str, Dict[str, Any]] = {}  # chat_id -> {"step": int, "last": datetime}

def load_state() -> None:
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

def save_state() -> None:
    out = {
        cid: {"step": st.get("step", 1), "last": st.get("last", datetime.min).isoformat()}
        for cid, st in USERS.items()
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Не удалось сохранить состояние: {e}")

# Запись в CSV «кто впервые нажал старт»
def _append_user_csv(chat_id: str, when: datetime) -> None:
    try:
        seen = set()
        if os.path.exists(USERS_CSV):
            with open(USERS_CSV, "r", newline="", encoding="utf-8") as f:
                for row in csv.reader(f):
                    if row:
                        seen.add(row[0])
        if chat_id not in seen:
            with open(USERS_CSV, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([chat_id, when.isoformat()])
    except Exception as e:
        log.warning(f"Не удалось обновить {USERS_CSV}: {e}")

# ===== КНОПКИ =====
def kb_for_lesson(n: int) -> InlineKeyboardMarkup:
    meta = LESSONS[n]
    rows: List[List[InlineKeyboardButton]] = []
    if meta.get("youtube"):
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=meta["youtube"])])
    if meta.get("video_file"):
        rows.append([InlineKeyboardButton("📥 Скачать видео (MP4, без сжатия)", callback_data=f"dl_video_{n}")])
    if meta.get("docs"):
        rows.append([InlineKeyboardButton("📎 Скачать материалы (PDF)", callback_data=f"dl_docs_{n}")])
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([])

# ===== ОТПРАВКА УРОКА (ТОЛЬКО ТЕКСТ + КНОПКИ) =====
async def send_lesson(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int) -> None:
    meta = LESSONS[n]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {meta['title']}\n\nВыбирай: смотреть на YouTube или скачать оригиналы кнопками ниже ⤵️",
        reply_markup=kb_for_lesson(n)
    )
    if n == 4 and meta.get("final_note"):
        await context.bot.send_message(chat_id=chat_id, text=meta["final_note"], reply_markup=kb_for_lesson(n))

# ===== КОМАНДЫ ПОЛЬЗОВАТЕЛЯ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    if chat_id not in USERS:
        USERS[chat_id] = {"step": 1, "last": datetime.now()}
        save_state()
        _append_user_csv(chat_id, USERS[chat_id]["last"])
        await update.message.reply_text("🚀 Стартуем. Твой первый урок готов 👇")
        await send_lesson(context, int(chat_id), 1)
    else:
        cur = USERS[chat_id]["step"]
        await update.message.reply_text("Мы уже начали. Твой текущий урок 👇")
        await send_lesson(context, int(chat_id), cur)

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

# ===== ОБРАБОТКА КНОПОК (ОТПРАВКА ФАЙЛОВ ПО ТРЕБОВАНИЮ) =====
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = (q.data or "").strip()
    chat_id = int(q.message.chat.id)

    # Скачать видео как документ (без сжатия)
    m = re.match(r"dl_video_(\d+)$", data)
    if m:
        n = int(m.group(1))
        meta = LESSONS.get(n, {})
        vname = meta.get("video_file")
        vpath = find_path(vname)
        if vpath:
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
            await context.bot.send_message(chat_id=chat_id, text=f"Видео не найдено: {vname or '—'}")
        return

    # Скачать все материалы
    m = re.match(r"dl_docs_(\d+)$", data)
    if m:
        n = int(m.group(1))
        docs = LESSONS.get(n, {}).get("docs") or []
        if not docs:
            await context.bot.send_message(chat_id=chat_id, text="Материалы отсутствуют.")
            return
        sent_any = False
        for dname in docs:
            dpath = find_path(dname)
            if dpath:
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
                await context.bot.send_message(chat_id=chat_id, text=f"Не найден: {dname}")
        if not sent_any:
            await context.bot.send_message(chat_id=chat_id, text="Материалы сейчас недоступны.")
        return

# ===== АДМИН-ХЕЛПЕРЫ и КОМАНДЫ =====
def _is_admin(chat_id: int) -> bool:
    return str(chat_id) in ADMIN_IDS

def _stats_counts() -> Tuple[int, Dict[int, int]]:
    total = len(USERS)
    by_step: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    for st in USERS.values():
        s = st.get("step", 1)
        by_step[s] = by_step.get(s, 0) + 1
    return total, by_step

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return
    if not USERS:
        await update.message.reply_text("Пока никто не нажимал /start.")
        return
    lines: List[str] = []
    for uid, st in USERS.items():
        step = st.get("step", 1)
        last = st.get("last")
        last_str = last.strftime("%Y-%m-%d %H:%M") if hasattr(last, "strftime") else str(last)
        lines.append(f"{uid} — урок {step} (последний: {last_str})")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 4000:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk)

async def stuck1_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return
    stuck = []
    for uid, st in USERS.items():
        if st.get("step", 1) == 1:
            last = st.get("last")
            last_str = last.strftime("%Y-%m-%d %H:%M") if hasattr(last, "strftime") else str(last)
            stuck.append(f"{uid} — урок 1 (последний: {last_str})")
    if not stuck:
        await update.message.reply_text("Никто не застрял на уроке 1 🎉")
        return
    chunk = ""
    for line in stuck:
        if len(chunk) + len(line) + 1 > 4000:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return
    total, by_step = _stats_counts()
    msg = (
        f"📊 Статистика\n"
        f"Всего пользователей: {total}\n"
        f"• Урок 1: {by_step.get(1,0)}\n"
        f"• Урок 2: {by_step.get(2,0)}\n"
        f"• Урок 3: {by_step.get(3,0)}\n"
        f"• Урок 4: {by_step.get(4,0)}\n"
    )
    await update.message.reply_text(msg)

async def checkfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return
    lines: List[str] = []
    lines.append("🗂 Проверка файлов (ищем в media/ и в корне)")
    for n, meta in LESSONS.items():
        title = meta.get("title", f"Урок {n}")
        vname = meta.get("video_file")
        vpath = find_path(vname) if vname else None
        lines.append(f"[{n}] {title}")
        lines.append(f"  video: {vname} -> {'OK' if vpath else 'NOT FOUND'}")
        for dname in meta.get("docs", []):
            dpath = find_path(dname)
            lines.append(f"  doc:   {dname} -> {'OK' if dpath else 'NOT FOUND'}")
    text = "\n".join(lines)
    while text:
        await update.message.reply_text(text[:3900])
        text = text[3900:]

async def exportusers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_chat.id):
        return
    if not os.path.exists(USERS_CSV):
        await update.message.reply_text("Файл с пользователями пока не создан.")
        return
    try:
        with open(USERS_CSV, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename="users.csv",
                caption="Список пользователей (chat_id, дата первого старта)"
            )
    except Exception as e:
        await update.message.reply_text(f"Не удалось отправить CSV: {e}")

# ===== АВТОВЫДАЧА КАЖДЫЕ 24 ЧАСА =====
async def tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now()
    for chat_id, st in list(USERS.items()):
        step = st.get("step", 1)
        last = st.get("last", datetime.min)
        if step < 4 and now - last >= timedelta(days=1):
            USERS[chat_id]["step"] = step + 1
            USERS[chat_id]["last"] = now
            save_state()
            await send_lesson(context, int(chat_id), USERS[chat_id]["step"])

# ===== ЗАПУСК =====
def main() -> None:
    load_state()
    app = ApplicationBuilder().token(TOKEN).build()

    # пользовательские команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_cmd))

    # обработка кнопок
    app.add_handler(CallbackQueryHandler(on_callback))

    # админ-команды
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("stuck1", stuck1_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("checkfiles", checkfiles_cmd))
    app.add_handler(CommandHandler("exportusers", exportusers_cmd))

    if app.job_queue is None:
        log.error('Нужен пакет: python-telegram-bot[job-queue]==20.7 в requirements.txt')
        raise SystemExit(1)
    app.job_queue.run_repeating(tick, interval=60, first=10)

    log.info("Бот запущен… (YouTube + кнопки скачивания, 1 урок/сутки, без авто-видео)")
    app.run_polling()

if __name__ == "__main__":
    main()
