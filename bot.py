def kb_for_lesson(n: int) -> InlineKeyboardMarkup | None:
    meta = LESSONS[n]
    rows = []
    if meta.get("youtube"):
        rows.append([InlineKeyboardButton("▶️ Смотреть на YouTube", url=meta["youtube"])])
    vid = meta.get("video")
    if vid and os.path.exists(vid):
        rows.append([InlineKeyboardButton("⬇️ Скачать видео (MP4)", callback_data=f"dl_video_{n}")])
    for text, url in meta.get("links", []):
        rows.append([InlineKeyboardButton(text, url=url)])
    return InlineKeyboardMarkup(rows) if rows else None

async def send_lesson(context: ContextTypes.DEFAULT_TYPE, chat_id: int, n: int):
    meta = LESSONS[n]
    # 1) Текст + кнопки
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⭐️ {meta['title']}\n\nВыбирай, как удобнее смотреть: YouTube или скачать видео. Бонусы ниже ⤵️",
        reply_markup=kb_for_lesson(n)
    )
    # 2) Авто-док
    file_path = meta.get("auto_file")
    if file_path:
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    await context.bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(file_path))
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить файл: {file_path}\n{e}")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"Файл не найден: {file_path}")
    # 3) Финал для 4-го
    if n == 4 and meta.get("final_note"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Связаться с Вадимом", url=f"https://t.me/{YOUR_USERNAME}")],
            [InlineKeyboardButton("🎵 «Маленькие шаги»", url=SONG_URL)],
            [InlineKeyboardButton("📺 Подписаться на YouTube «Главный Герой»", url=YOUTUBE_CHANNEL_URL)],
        ])
        await context.bot.send_message(chat_id=chat_id, text=meta["final_note"], reply_markup=kb)

# ---------- ХЭНДЛЕРЫ ----------
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

# ---------- ЕЖЕМИНУТНАЯ ПРОВЕРКА ----------
async def tick(context: ContextTypes.DEFAULT_TYPE):now = datetime.now()
    for chat_id, st in list(USERS.items()):
        step, last = st.get("step", 1), st.get("last", datetime.min)
        if step < 4 and now - last >= timedelta(days=1):
            USERS[chat_id]["step"] = step + 1
            USERS[chat_id]["last"] = now
            save_state()
            await send_lesson(context, int(chat_id), USERS[chat_id]["step"])

# ---------- ЗАПУСК ----------
def main():
    # диагностика старта
    log.info("Старт бота…")
    log.info(f"PWD: {os.getcwd()}")
    log.info(f"Файлы в корне: {', '.join(os.listdir('.'))}")
    load_state()

    app: Application = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    # Планировщик PTB: проверка каждые 60 сек
    app.job_queue.run_repeating(tick, interval=60, first=10)

    log.info("Бот запущен… (боевой режим: 1 урок/сутки)")
    app.run_polling()

if name == "__main__":
    main()
