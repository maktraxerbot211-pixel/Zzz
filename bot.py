import asyncio
import os
import re
from typing import Optional

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode

from sessions import (
    get_session, set_session, reset_session, soft_reset_session, SubtitleLine
)
from processing import (
    tmp_path, random_name, cleanup_file, cleanup_old_files,
    cut_video, merge_videos, merge_videos_with_crossfade,
    add_music_to_video, loop_video_to_fit_audio,
    get_video_duration, add_text_to_video,
    burn_subtitles_styled_ass, auto_subtitles_generate,
    generate_subtitle_preview_clip, apply_video_effect,
    generate_montage_preview_clip, mute_video, extract_audio,
    photo_to_video, format_srt_for_display, ms_to_srt_time, lines_to_srt,
)

TOKEN = os.environ.get("BOT_TOKEN", "8821262490:AAEHa1yLqLyLSa2sxo-eRifcSAcTNqg-IQA")

# ─── Keyboards ─────────────────────────────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✂️ Обрезать", callback_data="action_cut"),
         InlineKeyboardButton("🔗 Склеить", callback_data="action_merge")],
        [InlineKeyboardButton("🎵 Добавить музыку", callback_data="action_music"),
         InlineKeyboardButton("🎼 Вырезать музыку", callback_data="action_extract_music")],
        [InlineKeyboardButton("📝 Текст", callback_data="action_text"),
         InlineKeyboardButton("🔇 Убрать звук", callback_data="action_mute")],
        [InlineKeyboardButton("🤖 Авто субтитры", callback_data="action_auto_sub")],
        [InlineKeyboardButton("🎬 Авто монтаж", callback_data="action_montage")],
        [InlineKeyboardButton("✨ Улучшить видео", callback_data="action_enhance")],
        [InlineKeyboardButton("💧 Клеймо канала", callback_data="action_watermark"),
         InlineKeyboardButton("🗑 Сбросить всё", callback_data="action_reset")],
    ])

def continue_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Продолжить монтаж", callback_data="action_continue"),
         InlineKeyboardButton("🗑 Начать заново", callback_data="action_reset")],
    ])

def photo_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Добавить музыку к фото", callback_data="action_photo_music")],
        [InlineKeyboardButton("🗑 Сбросить всё", callback_data="action_reset")],
    ])

def words_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ 1 слово", callback_data="words_1"),
         InlineKeyboardButton("2️⃣ 2 слова", callback_data="words_2")],
        [InlineKeyboardButton("3️⃣ 3 слова", callback_data="words_3")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇦 Українська", callback_data="autosub_uk"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="autosub_ru")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="autosub_en"),
         InlineKeyboardButton("🌍 Авто", callback_data="autosub_auto")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def confirm_sub_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Всё правильно, выбрать анимацию!", callback_data="sub_confirm")],
        [InlineKeyboardButton("✏️ Редактировать строку", callback_data="sub_edit_line")],
        [InlineKeyboardButton("🗑 Отмена", callback_data="action_reset")],
    ])

def animation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬜ Без анимации", callback_data="anim_none")],
        [InlineKeyboardButton("🌊 Плавное появление (fade)", callback_data="anim_fade")],
        [InlineKeyboardButton("💥 Выскочить (pop)", callback_data="anim_pop")],
        [InlineKeyboardButton("⌨️ Слово за словом (накопление)", callback_data="anim_typewriter")],
        [InlineKeyboardButton("🎵 Группа слов → сброс (под музыку)", callback_data="anim_word_group")],
        [InlineKeyboardButton("🔔 Зум-пружина (zoom bounce)", callback_data="anim_zoom_bounce")],
        [InlineKeyboardButton("🎬 Из тумана (blur in)", callback_data="anim_blur_in")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def style_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Классика", callback_data="style_classic"),
         InlineKeyboardButton("🔥 Огонь", callback_data="style_fire")],
        [InlineKeyboardButton("💫 Неон", callback_data="style_neon"),
         InlineKeyboardButton("🖤 Минимал", callback_data="style_minimal")],
        [InlineKeyboardButton("💥 Жирный", callback_data="style_bold")],
        [InlineKeyboardButton("⬅️ Назад (анимация)", callback_data="sub_confirm"),
         InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def size_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔡 Маленький", callback_data="size_small"),
         InlineKeyboardButton("🔠 Средний", callback_data="size_medium")],
        [InlineKeyboardButton("🔤 Большой", callback_data="size_large"),
         InlineKeyboardButton("💬 Огромный", callback_data="size_xl")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def position_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬆️ Вверху", callback_data="pos_top")],
        [InlineKeyboardButton("⬛ По центру", callback_data="pos_center")],
        [InlineKeyboardButton("⬇️ Внизу (по умолчанию)", callback_data="pos_bottom")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def sub_preview_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Применить к полному видео!", callback_data="sub_apply")],
        [InlineKeyboardButton("🎨 Другой стиль", callback_data="sub_change_style"),
         InlineKeyboardButton("💫 Другая анимация", callback_data="sub_change_anim")],
        [InlineKeyboardButton("📍 Позиция", callback_data="sub_change_pos"),
         InlineKeyboardButton("🔠 Размер", callback_data="sub_change_size")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def montage_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔬 Плавный зум", callback_data="montage_smooth_zoom"),
         InlineKeyboardButton("🔍 Зум в", callback_data="montage_zoom_in")],
        [InlineKeyboardButton("🔎 Зум из", callback_data="montage_zoom_out"),
         InlineKeyboardButton("🌿 Живое изображение", callback_data="montage_living")],
        [InlineKeyboardButton("🎵 Бит-синхро", callback_data="montage_beat_sync"),
         InlineKeyboardButton("🌧 Дождь", callback_data="montage_rain")],
        [InlineKeyboardButton("➡️ Панорама →", callback_data="montage_pan_right"),
         InlineKeyboardButton("⬅️ Панорама ←", callback_data="montage_pan_left")],
        [InlineKeyboardButton("🎬 Кино", callback_data="montage_cinema"),
         InlineKeyboardButton("✨ Виньетка", callback_data="montage_vignette")],
        [InlineKeyboardButton("🌅 Тепло", callback_data="montage_warm"),
         InlineKeyboardButton("🖤 Ч/Б", callback_data="montage_bw")],
        [InlineKeyboardButton("🎨 Яркий", callback_data="montage_vivid"),
         InlineKeyboardButton("📡 Глитч", callback_data="montage_glitch")],
        [InlineKeyboardButton("🎞 Старое кино", callback_data="montage_old_film"),
         InlineKeyboardButton("💭 Сон", callback_data="montage_dream")],
        [InlineKeyboardButton("⚡ Ускорение x2", callback_data="montage_speed_up"),
         InlineKeyboardButton("🐌 Замедление x0.5", callback_data="montage_slow_down")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def montage_preview_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Применить к полному видео!", callback_data="montage_apply")],
        [InlineKeyboardButton("🔄 Другой эффект", callback_data="action_montage")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

def enhance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Авто улучшение", callback_data="montage_enhance_auto")],
        [InlineKeyboardButton("📺 HD (1280p + резкость)", callback_data="montage_enhance_hd")],
        [InlineKeyboardButton("🖥 Full HD (1080p + резкость)", callback_data="montage_enhance_fhd")],
        [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
    ])

# ─── Labels ────────────────────────────────────────────────────────────────────

STYLE_LABELS = {"classic": "🎬 Классика", "fire": "🔥 Огонь", "neon": "💫 Неон", "minimal": "🖤 Минимал", "bold": "💥 Жирный"}
ANIM_LABELS  = {"none": "⬜ Без анимации", "fade": "🌊 Плавное появление", "pop": "💥 Выскочить", "typewriter": "⌨️ Слово за словом", "word_group": "🎵 Группа слов → сброс", "zoom_bounce": "🔔 Зум-пружина", "blur_in": "🎬 Из тумана"}
SIZE_LABELS  = {"small": "🔡 Маленький", "medium": "🔠 Средний", "large": "🔤 Большой", "xl": "💬 Огромный"}
POS_LABELS   = {"bottom": "⬇️ Внизу", "center": "⬛ По центру", "top": "⬆️ Вверху"}
EFFECT_LABELS = {
    "rain": "🌧 Дождь", "zoom_in": "🔍 Зум в", "zoom_out": "🔎 Зум из", "smooth_zoom": "🔬 Плавный зум",
    "pan_right": "➡️ Панорама →", "pan_left": "⬅️ Панорама ←", "cinema": "🎬 Кино", "vignette": "✨ Виньетка",
    "warm": "🌅 Тепло", "bw": "🖤 Ч/Б", "vivid": "🎨 Яркий", "speed_up": "⚡ Ускорение x2",
    "slow_down": "🐌 Замедление x0.5", "beat_sync": "🎵 Бит-синхро", "living": "🌿 Живое изображение",
    "glitch": "📡 Глитч", "old_film": "🎞 Старое кино", "dream": "💭 Сон",
    "enhance_auto": "✨ Авто улучшение", "enhance_hd": "📺 HD (1280p)", "enhance_fhd": "🖥 Full HD (1080p)",
}

# ─── Helpers ───────────────────────────────────────────────────────────────────

async def safe_delete(bot, chat_id: int, message_id: Optional[int]):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)
    await safe_delete(context.bot, chat_id, session.last_menu_message_id)
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    set_session(user_id, last_menu_message_id=msg.message_id, chat_id=chat_id)

async def download_file(url: str, dest: str):
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    f.write(chunk)

async def get_file_url(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> str:
    file = await context.bot.get_file(file_id)
    return file.file_path

# ─── File handler ──────────────────────────────────────────────────────────────

async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, mime_type: str = "video/mp4"):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)

    wait_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Скачиваю файл...")
    try:
        is_audio = "audio" in mime_type or "ogg" in mime_type
        ext = "mp3" if is_audio else "mp4"
        local_path = tmp_path(random_name(ext))
        file_url = await get_file_url(context, file_id)
        await download_file(file_url, local_path)
        await safe_delete(context.bot, chat_id, wait_msg.message_id)

        if is_audio:
            if session.action == "awaiting_music" and session.last_video_path:
                video_dur = await get_video_duration(session.last_video_path)
                audio_dur = await get_video_duration(local_path)
                if audio_dur > video_dur + 3 and video_dur > 0:
                    set_session(user_id, pending_music_path=local_path, action="awaiting_loop_confirm")
                    diff = round(audio_dur - video_dur)
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🎵 Музыка ({round(audio_dur)}с) длиннее видео ({round(video_dur)}с) на {diff}с.\n\n🔁 *Зациклить видео под длину музыки?*",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔁 Да, зациклить видео", callback_data="loop_yes")],
                            [InlineKeyboardButton("✂️ Нет, обрезать музыку по видео", callback_data="loop_no")],
                            [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
                        ])
                    )
                    set_session(user_id, last_menu_message_id=msg.message_id)
                    return
                wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Накладываю музыку...")
                result = await add_music_to_video(session.last_video_path, local_path)
                await safe_delete(context.bot, chat_id, wm.message_id)
                await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Готово! Музыка добавлена.")
                cleanup_file(local_path)
                prev = session.last_video_path
                soft_reset_session(user_id, result)
                if prev and prev != result:
                    cleanup_file(prev)
                await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
                return
            if session.action == "awaiting_photo_music" and session.last_photo_path:
                wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Создаю видео из фото и музыки...")
                result = await photo_to_video(session.last_photo_path, local_path)
                await safe_delete(context.bot, chat_id, wm.message_id)
                await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Готово!")
                cleanup_file(local_path)
                soft_reset_session(user_id, result)
                await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
                return
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео/фото, потом выбери действие.")
            cleanup_file(local_path)
            return

        if session.action == "awaiting_merge_more":
            videos = list(session.videos) + [local_path]
            set_session(user_id, videos=videos, last_video_path=local_path)
            await safe_delete(context.bot, chat_id, session.last_menu_message_id)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"📹 Видео добавлено (всего: {len(videos)}). Отправь ещё или склей:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"🔗 Склеить сейчас ({len(videos)})", callback_data="do_merge")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
                ])
            )
            set_session(user_id, last_menu_message_id=msg.message_id)
            return

        if session.last_video_path and session.action == "idle":
            set_session(user_id, pending_new_video=local_path)
            await safe_delete(context.bot, chat_id, session.last_menu_message_id)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text="📹 У тебя уже загружено видео.\n\nЧто сделать с новым?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Заменить текущее", callback_data="replace_video"),
                     InlineKeyboardButton("➕ Добавить к склейке", callback_data="add_to_merge")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
                ])
            )
            set_session(user_id, last_menu_message_id=msg.message_id)
            return

        set_session(user_id, last_video_path=local_path, videos=[local_path], action="idle")
        await send_menu(update, context, "✅ Видео получено! Что делаем?", main_menu())

    except Exception as e:
        await safe_delete(context.bot, chat_id, wait_msg.message_id)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка при скачивании: {e}")

# ─── Subtitle preview helper ───────────────────────────────────────────────────

async def show_subtitle_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)
    if not session.last_video_path or not session.srt_lines or not session.subtitle_style or session.subtitle_animation is None:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так. Начни заново.")
        return
    position = session.subtitle_position or "bottom"
    size = session.subtitle_size or "medium"
    set_session(user_id, action="awaiting_subtitle_preview")
    wm = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ Генерирую превью 5 секунд...\nСтиль: {STYLE_LABELS[session.subtitle_style]} | Анимация: {ANIM_LABELS[session.subtitle_animation]} | Позиция: {POS_LABELS[position]} | Размер: {SIZE_LABELS[size]}"
    )
    try:
        preview = await generate_subtitle_preview_clip(session.last_video_path, session.srt_lines, session.subtitle_style, session.subtitle_animation, position, session.watermark_text, size)
        await safe_delete(context.bot, chat_id, wm.message_id)
        await context.bot.send_video(
            chat_id=chat_id, video=open(preview, "rb"),
            caption=f"👆 Превью 5 секунд\n\nСтиль: {STYLE_LABELS[session.subtitle_style]}\nАнимация: {ANIM_LABELS[session.subtitle_animation]}\nПозиция: {POS_LABELS[position]}\nРазмер: {SIZE_LABELS[size]}\n\nВсё нравится? Нажми ✅",
            reply_markup=sub_preview_menu()
        )
        cleanup_file(preview)
    except Exception as err:
        await safe_delete(context.bot, chat_id, wm.message_id)
        await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при генерации превью. Попробуй другой стиль.")
        set_session(user_id, action="awaiting_subtitle_style")
        await context.bot.send_message(chat_id=chat_id, text="🎨 Выбери стиль:", reply_markup=style_menu())

# ─── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(update.effective_user.id)
    await update.message.reply_text(
        "👋 Привет! Я бот-монтажор.\n\n"
        "Отправь видео и выбери действие:\n\n"
        "🤖 *Авто субтитры* — Whisper распознаёт речь → проверяешь → выбираешь позицию, анимацию и стиль → превью → готово!\n"
        "🎬 *Авто монтаж* — 18 эффектов: зум, панорама, дождь, кино, ч/б и другие + превью перед применением\n"
        "💧 *Клеймо канала* — полупрозрачный текст внизу по центру\n\n"
        "После обработки видео *остаётся загруженным* — сразу применяй следующий эффект!",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu()
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "*Авто субтитры:*\n"
        "1. Выбери кол-во слов → язык\n"
        "2. Бот распознаёт речь (1-3 мин)\n"
        "3. Проверяй и редактируй строки:\n"
        "   `5 исправленный текст` — меняет строку 5\n"
        "4. ✅ → анимация → стиль → позиция → превью → применить\n\n"
        "*Авто монтаж:* 18 эффектов с превью\n\n"
        "*Клеймо:* /watermark НАЗВАНИЕ — установить\n"
        "/watermark off — убрать\n\n"
        "*Продолжение монтажа:* после каждой операции видео остаётся.\n\n"
        "/reset — сбросить всё",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(update.effective_user.id)
    try:
        await update.message.delete()
    except Exception:
        pass
    await send_menu(update, context, "♻️ Сброшено. Отправь новое видео.", main_menu())

async def cmd_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        await update.message.delete()
    except Exception:
        pass
    text = update.message.text.replace("/watermark", "", 1).strip()
    if not text:
        current = get_session(user_id).watermark_text
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"💧 *Клеймо канала*\n\nТекущее: _{current}_\n\nИспользование:\n/watermark Название канала\n/watermark off — убрать" if current else "💧 *Клеймо канала*\n\nНе установлено.\n\nИспользование:\n/watermark Название канала",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    if text.lower() == "off":
        set_session(user_id, watermark_text=None)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Клеймо убрано.")
    else:
        set_session(user_id, watermark_text=text)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ Клеймо установлено: _{text}_\n\nБудет добавляться на все готовые видео.", parse_mode=ParseMode.MARKDOWN)

# ─── Media handlers ────────────────────────────────────────────────────────────

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception:
        pass
    await handle_video_file(update, context, update.message.video.file_id, "video/mp4")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception:
        pass
    doc = update.message.document
    mime = doc.mime_type or ""
    if mime.startswith("video/") or mime.startswith("audio/"):
        await handle_video_file(update, context, doc.file_id, mime)
    else:
        await update.message.reply_text("⚠️ Отправь видео или аудио файл.")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception:
        pass
    msg = update.message
    file_id = (msg.audio or msg.voice).file_id
    await handle_video_file(update, context, file_id, "audio/mpeg")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except Exception:
        pass
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)
    photo = update.message.photo[-1]
    wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Скачиваю фото...")
    try:
        local_path = tmp_path(random_name("jpg"))
        file_url = await get_file_url(context, photo.file_id)
        await download_file(file_url, local_path)
        await safe_delete(context.bot, chat_id, wm.message_id)
        if session.action == "idle" and session.music:
            wm2 = await context.bot.send_message(chat_id=chat_id, text="⏳ Создаю видео из фото и музыки...")
            result = await photo_to_video(local_path, session.music)
            await safe_delete(context.bot, chat_id, wm2.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Готово!")
            cleanup_file(local_path)
            soft_reset_session(user_id, result)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
            return
        set_session(user_id, last_photo_path=local_path, action="idle")
        await send_menu(update, context, "✅ Фото получено!", photo_menu())
    except Exception as e:
        await safe_delete(context.bot, chat_id, wm.message_id)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Ошибка при скачивании фото: {e}")

# ─── Text input handler ────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    try:
        await update.message.delete()
    except Exception:
        pass

    if session.action == "awaiting_watermark_text":
        if text.lower() in ("off", "нет"):
            set_session(user_id, watermark_text=None, action="idle")
            await context.bot.send_message(chat_id=chat_id, text="✅ Клеймо убрано.")
        else:
            set_session(user_id, watermark_text=text, action="idle")
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Клеймо: _{text}_", parse_mode=ParseMode.MARKDOWN)
        await send_menu(update, context, "Что делаем?", main_menu())
        return

    if session.action == "awaiting_cut_start":
        set_session(user_id, cut_start=text, action="awaiting_cut_end")
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Начало: `{text}`\n\nТеперь время конца:", parse_mode=ParseMode.MARKDOWN)
        return

    if session.action == "awaiting_cut_end":
        cut_start = session.cut_start
        set_session(user_id, action="idle")
        wm = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Обрезаю `{cut_start}` → `{text}`...", parse_mode=ParseMode.MARKDOWN)
        try:
            result = await cut_video(session.last_video_path, cut_start, text)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption=f"✅ Обрезано: {cut_start} → {text}")
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка. Формат: `0:10` или `00:00:10`", parse_mode=ParseMode.MARKDOWN)
            set_session(user_id, action="awaiting_cut_start")
        return

    if session.action == "awaiting_text_content":
        set_session(user_id, text_content=text, action="awaiting_text_position")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 Текст: *{text}*\n\nПозиция:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬆️ Сверху", callback_data="text_top")],
                [InlineKeyboardButton("⬛ По центру", callback_data="text_center")],
                [InlineKeyboardButton("⬇️ Снизу", callback_data="text_bottom")],
            ])
        )
        return

    if session.action == "awaiting_sub_linenum":
        try:
            num = int(text.strip())
        except ValueError:
            num = -1
        srt_lines = session.srt_lines or []
        if num < 1 or num > len(srt_lines):
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Введи корректный номер строки (1–{len(srt_lines)}):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="sub_cancel_edit")]])
            )
            return
        line = next((l for l in srt_lines if l.index == num), None)
        set_session(user_id, action="awaiting_sub_newtext", editing_line_num=num)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✏️ *Строка {num}*\n\nТекущий текст:\n_{line.text if line else '—'}_\n\nВведи новый текст:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="sub_cancel_edit")]])
        )
        return

    if session.action == "awaiting_sub_newtext" and session.editing_line_num is not None and session.srt_lines:
        lines = list(session.srt_lines)
        line_num = session.editing_line_num
        idx = next((i for i, l in enumerate(lines) if l.index == line_num), -1)
        if idx != -1:
            lines[idx] = SubtitleLine(lines[idx].index, lines[idx].start_ms, lines[idx].end_ms, text)
            srt_path = tmp_path(random_name("srt"))
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(lines_to_srt(lines))
            if session.srt_path:
                cleanup_file(session.srt_path)
            set_session(user_id, srt_lines=lines, srt_path=srt_path, action="awaiting_subtitle_confirm", editing_line_num=None)
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Строка {line_num} обновлена:\n_{text}_\n\nМожно редактировать ещё или нажми ✅", parse_mode=ParseMode.MARKDOWN, reply_markup=confirm_sub_menu())
        else:
            set_session(user_id, action="awaiting_subtitle_confirm", editing_line_num=None)
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Строка {line_num} не найдена.", reply_markup=confirm_sub_menu())
        return

    if session.action == "awaiting_subtitle_confirm" and session.srt_lines:
        lines = list(session.srt_lines)
        applied = []
        failed = []
        for row in text.split("\n"):
            row = row.strip()
            if not row:
                continue
            m = re.match(r'^(\d+)\s+(.+)$', row)
            if not m:
                if len(text.split("\n")) == 1:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="💡 *Как редактировать:*\n\nНажми *✏️ Редактировать строку* или введи `5 Новый текст`\n\nИли нажми ✅ если всё правильно.",
                        parse_mode=ParseMode.MARKDOWN, reply_markup=confirm_sub_menu()
                    )
                    return
                failed.append(f'"{row}" — не понял формат')
                continue
            line_num = int(m.group(1))
            new_text = m.group(2).strip()
            idx = next((i for i, l in enumerate(lines) if l.index == line_num), -1)
            if idx == -1:
                failed.append(f"строка {line_num} — не найдена")
            else:
                lines[idx] = SubtitleLine(lines[idx].index, lines[idx].start_ms, lines[idx].end_ms, new_text)
                applied.append(f"{line_num}. {new_text}")
        if not applied and failed:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Не удалось:\n{chr(10).join(failed)}", reply_markup=confirm_sub_menu())
            return
        srt_path = tmp_path(random_name("srt"))
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(lines_to_srt(lines))
        if session.srt_path:
            cleanup_file(session.srt_path)
        set_session(user_id, srt_lines=lines, srt_path=srt_path)
        reply = f"✏️ Исправлено {len(applied)} строк:\n" + "\n".join(f"• {a}" for a in applied)
        if failed:
            reply += f"\n\n⚠️ Не найдено:\n" + "\n".join(failed)
        reply += "\n\nМожно исправить ещё или нажми ✅"
        await context.bot.send_message(chat_id=chat_id, text=reply, reply_markup=confirm_sub_menu())
        return

    await send_menu(update, context, "Отправь видео или выбери действие:", main_menu())

# ─── Callback query handlers ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)

    # ── Reset / Continue ──
    if data == "action_reset":
        reset_session(user_id)
        await send_menu(update, context, "♻️ Сброшено. Отправь новое видео.", main_menu())
        return
    if data == "action_continue":
        await send_menu(update, context, "Что делаем с видео?", main_menu())
        return

    # ── Replace / Add to merge ──
    if data == "replace_video":
        new_path = session.pending_new_video
        if not new_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так.")
            return
        if session.last_video_path:
            cleanup_file(session.last_video_path)
        set_session(user_id, last_video_path=new_path, videos=[new_path], action="idle", pending_new_video=None)
        await send_menu(update, context, "✅ Видео заменено! Что делаем?", main_menu())
        return
    if data == "add_to_merge":
        new_path = session.pending_new_video
        if not new_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так.")
            return
        videos = list(session.videos or []) + [new_path]
        set_session(user_id, videos=videos, action="awaiting_merge_more", pending_new_video=None)
        await safe_delete(context.bot, chat_id, session.last_menu_message_id)
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"📹 Видео добавлено (всего: {len(videos)}). Отправь ещё или склей:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔗 Склеить сейчас ({len(videos)})", callback_data="do_merge")],
                [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
            ])
        )
        set_session(user_id, last_menu_message_id=msg.message_id)
        return

    # ── Cut ──
    if data == "action_cut":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        set_session(user_id, action="awaiting_cut_start")
        await context.bot.send_message(chat_id=chat_id, text="✂️ *Обрезка*\n\nВведи время начала (например `0:30` или `90`):", parse_mode=ParseMode.MARKDOWN)
        return

    # ── Merge ──
    if data == "action_merge":
        current = [session.last_video_path] if session.last_video_path else []
        set_session(user_id, action="awaiting_merge_more", videos=current)
        await context.bot.send_message(chat_id=chat_id, text="🔗 Есть 1 видео. Отправь следующее." if current else "🔗 Отправь первое видео.")
        return
    if data == "do_merge":
        if len(session.videos) < 2:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нужно минимум 2 видео.")
            return
        await safe_delete(context.bot, chat_id, session.last_menu_message_id)
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔗 *Как склеить {len(session.videos)} видео?*\n\n🌊 *Плавный переход* — crossfade, стык не виден\n✂️ *Обычная склейка* — мгновенный переход",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌊 Плавный переход (crossfade)", callback_data="merge_crossfade")],
                [InlineKeyboardButton("✂️ Обычная склейка", callback_data="merge_hardcut")],
                [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
            ])
        )
        set_session(user_id, last_menu_message_id=msg.message_id)
        return
    if data == "merge_crossfade":
        await safe_delete(context.bot, chat_id, session.last_menu_message_id)
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="🌊 *Длительность перехода:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ 0.3 сек (быстро)", callback_data="crossfade_0.3"),
                 InlineKeyboardButton("🌊 0.5 сек (норм)", callback_data="crossfade_0.5")],
                [InlineKeyboardButton("🐌 1.0 сек (медленно)", callback_data="crossfade_1.0"),
                 InlineKeyboardButton("💫 2.0 сек (очень плавно)", callback_data="crossfade_2.0")],
                [InlineKeyboardButton("❌ Отмена", callback_data="action_reset")],
            ])
        )
        set_session(user_id, last_menu_message_id=msg.message_id)
        return
    if data.startswith("crossfade_"):
        dur = float(data.split("_")[1])
        if len(session.videos) < 2:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нужно минимум 2 видео.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Склеиваю с плавным переходом {dur} сек...")
        try:
            result = await merge_videos_with_crossfade(session.videos, dur)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption=f"✅ Склеено {len(session.videos)} видео с плавным переходом {dur} сек 🌊")
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при склейке с переходом.")
        return
    if data == "merge_hardcut":
        if len(session.videos) < 2:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нужно минимум 2 видео.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Склеиваю...")
        try:
            result = await merge_videos(session.videos)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption=f"✅ Склеено {len(session.videos)} видео.")
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при склейке.")
        return

    # ── Music ──
    if data == "action_music":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        set_session(user_id, action="awaiting_music")
        await context.bot.send_message(chat_id=chat_id, text="🎵 Отправь аудио файл (MP3, OGG, WAV).")
        return
    if data == "loop_yes":
        if not session.last_video_path or not session.pending_music_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Зацикливаю видео под длину музыки... 🔁")
        try:
            result = await loop_video_to_fit_audio(session.last_video_path, session.pending_music_path)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Готово! Видео зациклено 🔁")
            cleanup_file(session.pending_music_path)
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при зацикливании.")
        return
    if data == "loop_no":
        if not session.last_video_path or not session.pending_music_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Накладываю музыку...")
        try:
            result = await add_music_to_video(session.last_video_path, session.pending_music_path)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Готово! Музыка добавлена.")
            cleanup_file(session.pending_music_path)
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при добавлении музыки.")
        return

    # ── Text overlay ──
    if data == "action_text":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        set_session(user_id, action="awaiting_text_content")
        await context.bot.send_message(chat_id=chat_id, text="📝 Введи текст для наложения на видео:")
        return
    if data in ("text_top", "text_center", "text_bottom"):
        pos = data.split("_")[1]
        if not session.last_video_path or not session.text_content:
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Добавляю текст...")
        try:
            result = await add_text_to_video(session.last_video_path, session.text_content, pos)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="✅ Текст добавлен.")
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при добавлении текста.")
        return

    # ── Mute ──
    if data == "action_mute":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Убираю звук...")
        try:
            result = await mute_video(session.last_video_path)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption="🔇 Готово! Видео без звука.")
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при удалении звука.")
        return

    # ── Extract music ──
    if data == "action_extract_music":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Извлекаю аудио...")
        try:
            result = await extract_audio(session.last_video_path)
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_audio(chat_id=chat_id, audio=open(result, "rb"), caption="✅ Аудио извлечено!")
            cleanup_file(result)
            await send_menu(update, context, "Что делаем дальше?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при извлечении аудио.")
        return

    # ── Photo music ──
    if data == "action_photo_music":
        set_session(user_id, action="awaiting_photo_music")
        await context.bot.send_message(chat_id=chat_id, text="🎵 Отправь аудио файл для слайдшоу из фото:")
        return

    # ── Watermark ──
    if data == "action_watermark":
        set_session(user_id, action="awaiting_watermark_text")
        current = session.watermark_text
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"💧 *Клеймо канала*\n\nТекущее: _{current}_\n\nВведи новое название или «off» чтобы убрать:" if current else "💧 *Клеймо канала*\n\nВведи название канала:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Auto subtitles ──
    if data == "action_auto_sub":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        await context.bot.send_message(chat_id=chat_id, text="🤖 *Авто субтитры*\n\nСколько слов показывать за раз?", parse_mode=ParseMode.MARKDOWN, reply_markup=words_menu())
        return
    if data in ("words_1", "words_2", "words_3"):
        n = int(data[-1])
        set_session(user_id, words_per_line=n)
        await context.bot.send_message(chat_id=chat_id, text="🌍 Выбери язык речи:", reply_markup=language_menu())
        return
    if data in ("autosub_uk", "autosub_ru", "autosub_en", "autosub_auto"):
        lang_map = {"autosub_uk": "Ukrainian", "autosub_ru": "Russian", "autosub_en": "English", "autosub_auto": "auto"}
        language = lang_map[data]
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нет видео.")
            return
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ Распознаю речь...\n_Whisper анализирует аудио — 1-3 минуты._", parse_mode=ParseMode.MARKDOWN)
        try:
            srt_lines, srt_path = await auto_subtitles_generate(session.last_video_path, language, session.words_per_line)
            set_session(user_id, srt_lines=srt_lines, srt_path=srt_path, action="awaiting_subtitle_confirm")
            await safe_delete(context.bot, chat_id, wm.message_id)
            all_lines = format_srt_for_display(srt_lines)
            header = f"📝 *Субтитры готовы!* ({len(srt_lines)} строк)\n\n*Как редактировать:*\nОдну строку: `5 Новый текст`\n\n⚠️ *Проверь ВСЕ строки!*"
            MAX_CHUNK = 3800
            if len(all_lines) <= MAX_CHUNK:
                await context.bot.send_message(chat_id=chat_id, text=f"{header}\n\n```\n{all_lines}\n```", parse_mode=ParseMode.MARKDOWN, reply_markup=confirm_sub_menu())
            else:
                chunks = []
                cur = ""
                for line in all_lines.split("\n"):
                    if len(cur + "\n" + line) > MAX_CHUNK:
                        chunks.append(cur)
                        cur = line
                    else:
                        cur = cur + "\n" + line if cur else line
                if cur:
                    chunks.append(cur)
                await context.bot.send_message(chat_id=chat_id, text=f"{header}\n\n📄 Показываю {len(srt_lines)} строк по частям:", parse_mode=ParseMode.MARKDOWN)
                for i, chunk in enumerate(chunks):
                    is_last = i == len(chunks) - 1
                    await context.bot.send_message(
                        chat_id=chat_id, text=f"```\n{chunk}\n```", parse_mode=ParseMode.MARKDOWN,
                        reply_markup=confirm_sub_menu() if is_last else None
                    )
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка распознавания речи. Убедись что в видео есть чёткая речь.")
        return

    # ── Subtitle edit line ──
    if data == "sub_edit_line":
        if not session.srt_lines:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нет субтитров. Начни заново.")
            return
        set_session(user_id, action="awaiting_sub_linenum")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✏️ *Редактировать строку*\n\nВведи *номер строки* (1–{len(session.srt_lines)}):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="sub_cancel_edit")]])
        )
        return
    if data == "sub_cancel_edit":
        set_session(user_id, action="awaiting_subtitle_confirm", editing_line_num=None)
        await context.bot.send_message(chat_id=chat_id, text="↩️ Редактирование отменено.", reply_markup=confirm_sub_menu())
        return

    # ── Subtitle confirm → animation ──
    if data == "sub_confirm":
        if not session.srt_lines:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Нет субтитров. Начни заново.")
            return
        set_session(user_id, action="awaiting_subtitle_animation")
        await context.bot.send_message(
            chat_id=chat_id,
            text="💫 *Выбери анимацию субтитров:*\n\n⬜ *Без анимации* — просто появляются\n🌊 *Плавное появление* — fade\n💥 *Выскочить* — pop\n⌨️ *Слово за словом* — накапливаются\n🎵 *Группа слов → сброс* — под музыку\n🔔 *Зум-пружина* — выпрыгивает с отскоком\n🎬 *Из тумана* — из размытия",
            parse_mode=ParseMode.MARKDOWN, reply_markup=animation_menu()
        )
        return

    # ── Animation select ──
    anim_map = {"anim_none": "none", "anim_fade": "fade", "anim_pop": "pop", "anim_typewriter": "typewriter", "anim_word_group": "word_group", "anim_zoom_bounce": "zoom_bounce", "anim_blur_in": "blur_in"}
    if data in anim_map:
        set_session(user_id, subtitle_animation=anim_map[data], action="awaiting_subtitle_style")
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎨 *Выбери стиль субтитров:*\n\n🎬 *Классика* — белый, чёрная обводка\n🔥 *Огонь* — оранжевый яркий\n💫 *Неон* — жёлтый с неоновой обводкой\n🖤 *Минимал* — серый тонкий\n💥 *Жирный* — огромный белый",
            parse_mode=ParseMode.MARKDOWN, reply_markup=style_menu()
        )
        return

    # ── Style select ──
    style_map = {"style_classic": "classic", "style_fire": "fire", "style_neon": "neon", "style_minimal": "minimal", "style_bold": "bold"}
    if data in style_map:
        set_session(user_id, subtitle_style=style_map[data], action="awaiting_subtitle_position")
        await context.bot.send_message(chat_id=chat_id, text="📍 *Позиция субтитров:*\n\nГде будут отображаться?", parse_mode=ParseMode.MARKDOWN, reply_markup=position_menu())
        return

    # ── Position select ──
    pos_map = {"pos_bottom": "bottom", "pos_center": "center", "pos_top": "top"}
    if data in pos_map:
        set_session(user_id, subtitle_position=pos_map[data], action="awaiting_subtitle_size")
        await context.bot.send_message(chat_id=chat_id, text="🔠 *Размер субтитров:*", parse_mode=ParseMode.MARKDOWN, reply_markup=size_menu())
        return

    # ── Size select → preview ──
    size_map = {"size_small": "small", "size_medium": "medium", "size_large": "large", "size_xl": "xl"}
    if data in size_map:
        set_session(user_id, subtitle_size=size_map[data])
        await show_subtitle_preview(update, context)
        return

    # ── Preview nav ──
    if data == "sub_change_style":
        set_session(user_id, action="awaiting_subtitle_style")
        await context.bot.send_message(chat_id=chat_id, text="🎨 Выбери стиль:", reply_markup=style_menu())
        return
    if data == "sub_change_anim":
        set_session(user_id, action="awaiting_subtitle_animation")
        await context.bot.send_message(chat_id=chat_id, text="💫 Выбери анимацию:", reply_markup=animation_menu())
        return
    if data == "sub_change_pos":
        set_session(user_id, action="awaiting_subtitle_position")
        await context.bot.send_message(chat_id=chat_id, text="📍 Выбери позицию:", reply_markup=position_menu())
        return
    if data == "sub_change_size":
        set_session(user_id, action="awaiting_subtitle_size")
        await context.bot.send_message(chat_id=chat_id, text="🔠 Размер субтитров:", reply_markup=size_menu())
        return

    # ── Apply subtitles ──
    if data == "sub_apply":
        if not session.last_video_path or not session.srt_lines or not session.subtitle_style or session.subtitle_animation is None:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так. Начни заново.")
            return
        position = session.subtitle_position or "bottom"
        size = session.subtitle_size or "medium"
        wm = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Записываю субтитры...\nСтиль: {STYLE_LABELS[session.subtitle_style]} | Анимация: {ANIM_LABELS[session.subtitle_animation]} | Позиция: {POS_LABELS[position]} | Размер: {SIZE_LABELS[size]}"
        )
        try:
            result = await burn_subtitles_styled_ass(session.last_video_path, session.srt_lines, session.subtitle_style, session.subtitle_animation, position, session.watermark_text, size)
            await safe_delete(context.bot, chat_id, wm.message_id)
            caption = f"✅ Готово!\nСтиль: {STYLE_LABELS[session.subtitle_style]}\nАнимация: {ANIM_LABELS[session.subtitle_animation]}\nПозиция: {POS_LABELS[position]}\nРазмер: {SIZE_LABELS[size]}"
            if session.watermark_text:
                caption += f"\n💧 Клеймо: {session.watermark_text}"
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption=caption)
            if session.srt_path:
                cleanup_file(session.srt_path)
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при записи субтитров. Попробуй другой стиль.")
            set_session(user_id, action="awaiting_subtitle_style")
            await context.bot.send_message(chat_id=chat_id, text="🎨 Выбери стиль:", reply_markup=style_menu())
        return

    # ── Enhance ──
    if data == "action_enhance":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        await context.bot.send_message(
            chat_id=chat_id,
            text="✨ *Улучшение видео*\n\n*Авто* — резкость + шумодав\n*HD* — масштаб до 1280p\n*Full HD* — масштаб до 1080p\n\nПокажу превью перед применением.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=enhance_menu()
        )
        return
    if data in ("montage_enhance_auto", "montage_enhance_hd", "montage_enhance_fhd"):
        effect = data.replace("montage_", "")
        await handle_montage_select(update, context, effect)
        return

    # ── Montage ──
    if data == "action_montage":
        if not session.last_video_path:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Сначала отправь видео.")
            return
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎬 *Авто монтаж* — выбери эффект:\n\nПосле выбора покажу *превью 5 секунд*.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=montage_menu()
        )
        return

    montage_effects = {
        "montage_rain": "rain", "montage_zoom_in": "zoom_in", "montage_zoom_out": "zoom_out",
        "montage_smooth_zoom": "smooth_zoom", "montage_pan_right": "pan_right", "montage_pan_left": "pan_left",
        "montage_cinema": "cinema", "montage_vignette": "vignette", "montage_warm": "warm",
        "montage_bw": "bw", "montage_vivid": "vivid", "montage_speed_up": "speed_up",
        "montage_slow_down": "slow_down", "montage_beat_sync": "beat_sync", "montage_living": "living",
        "montage_glitch": "glitch", "montage_old_film": "old_film", "montage_dream": "dream",
    }
    if data in montage_effects:
        await handle_montage_select(update, context, montage_effects[data])
        return

    if data == "montage_apply":
        if not session.last_video_path or not session.pending_montage_effect:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Что-то пошло не так. Выбери эффект заново.")
            return
        effect = session.pending_montage_effect
        wm = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Применяю «{EFFECT_LABELS[effect]}» к полному видео...")
        try:
            result = await apply_video_effect(session.last_video_path, effect, session.watermark_text)
            await safe_delete(context.bot, chat_id, wm.message_id)
            caption = f"✅ Готово! Эффект: {EFFECT_LABELS[effect]}"
            if session.watermark_text:
                caption += f"\n💧 Клеймо: {session.watermark_text}"
            await context.bot.send_video(chat_id=chat_id, video=open(result, "rb"), caption=caption)
            prev = session.last_video_path
            soft_reset_session(user_id, result)
            if prev and prev != result:
                cleanup_file(prev)
            await send_menu(update, context, "Продолжить монтаж или начать заново?", continue_menu())
        except Exception as e:
            await safe_delete(context.bot, chat_id, wm.message_id)
            await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при применении эффекта.", reply_markup=montage_menu())
        return

async def handle_montage_select(update: Update, context: ContextTypes.DEFAULT_TYPE, effect: str):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    session = get_session(user_id)
    if not session.last_video_path:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Нет видео.")
        return
    set_session(user_id, pending_montage_effect=effect, action="awaiting_montage_preview")
    if effect == "beat_sync":
        wm = await context.bot.send_message(chat_id=chat_id, text="⏳ *Бит-синхро*: анализирую аудио, нахожу биты... (~30-60 сек)", parse_mode=ParseMode.MARKDOWN)
    else:
        wm = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Генерирую превью «{EFFECT_LABELS[effect]}» (5 сек)...")
    try:
        preview = await generate_montage_preview_clip(session.last_video_path, effect)
        await safe_delete(context.bot, chat_id, wm.message_id)
        await context.bot.send_video(
            chat_id=chat_id, video=open(preview, "rb"),
            caption=f"👆 Превью: {EFFECT_LABELS[effect]}\n\nНравится? Нажми ✅",
            reply_markup=montage_preview_menu()
        )
        cleanup_file(preview)
    except Exception as e:
        await safe_delete(context.bot, chat_id, wm.message_id)
        await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка при генерации превью. Попробуй другой эффект.", reply_markup=montage_menu())
        set_session(user_id, action="idle")

# ─── Cleanup job ──────────────────────────────────────────────────────────────────

async def job_cleanup_tmp(context: ContextTypes.DEFAULT_TYPE):
    removed = cleanup_old_files(max_age_seconds=3600)
    if removed:
    print(f"[cleanup] Удалено {removed} старых файлов из /tmp/tgbot")

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("watermark", cmd_watermark))

    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(handle_callback))


    job_queue = app.job_queue
    job_queue.run_repeating(job_cleanup_tmp, interval=3600, first=300)
    print("Bot started (long polling)...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
