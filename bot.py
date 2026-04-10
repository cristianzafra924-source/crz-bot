import os
import json
import base64
import asyncio
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OWNER_CHAT_ID  = int(os.environ.get("OWNER_CHAT_ID", "1702730646"))
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO    = "cristianzafra924-source/mt5-analyzer"
GITHUB_BRANCH  = "principal"
GITHUB_API     = "https://api.github.com"

# ── Session state ─────────────────────────────────────────────────────────────
session = {
    "mode": None,          # "analisis" | "video"
    "semana": None,
    "activo": None,
    "texto": None,
    "imagen": None,        # bytes
    "imagen_nombre": None,
    "audio": None,         # bytes
    "audio_nombre": None,
}

# ── GitHub helpers ────────────────────────────────────────────────────────────
def github_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def get_file_sha(path):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers=github_headers(), params={"ref": GITHUB_BRANCH})
    if r.status_code == 200:
        return r.json().get("sha")
    return None

def upload_file(path, content_bytes, message):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    sha = get_file_sha(path)
    data = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "branch": GITHUB_BRANCH
    }
    if sha:
        data["sha"] = sha
    r = requests.put(url, headers=github_headers(), json=data)
    return r.status_code in (200, 201)

def get_app_py():
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/aplicaci%C3%B3n.py"
    r = requests.get(url, headers=github_headers(), params={"ref": GITHUB_BRANCH})
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    return None, None

def update_app_py(new_content, sha, commit_msg):
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/aplicaci%C3%B3n.py"
    data = {
        "message": commit_msg,
        "content": base64.b64encode(new_content.encode("utf-8")).decode(),
        "sha": sha,
        "branch": GITHUB_BRANCH
    }
    r = requests.put(url, headers=github_headers(), json=data)
    return r.status_code in (200, 201)

def add_analisis_to_app(semana, activo, img_nombre, audio_nombre, texto, img_b64, audio_b64):
    content, sha = get_app_py()
    if not content:
        return False

    new_block = f'''        {{
            "semana":  "{semana}",
            "activo":  "{activo}",
            "img_b64": "{img_b64}",
            "img_fmt": "image/png",
            "audio_b64": "{audio_b64}",
            "audio_fmt": "audio/ogg",
            "texto":   "{texto}",
        }},'''

    # Insert after the last }, in analisis_fijos
    marker = "    analisis_fijos = ["
    if marker not in content:
        return False

    # Find the closing ] of analisis_fijos
    start = content.find(marker)
    bracket_end = content.find("\n    ]\n", start)
    if bracket_end == -1:
        return False

    insert_pos = bracket_end
    new_content = content[:insert_pos] + "\n" + new_block + content[insert_pos:]
    return update_app_py(new_content, sha, f"🤖 Bot: Añadir análisis {activo} {semana}")

def add_video_to_app(titulo, fecha, url_video, codigo, desc):
    content, sha = get_app_py()
    if not content:
        return False

    new_block = f'''        {{
            "id":      "video_{datetime.now().strftime('%Y%m%d')}",
            "titulo":  "{titulo}",
            "fecha":   "{fecha}",
            "desc":    "{desc}",
            "url":     "{url_video}",
            "codigo":  "{codigo}",
        }},'''

    marker = "    videos = ["
    if marker not in content:
        return False

    start = content.find(marker)
    bracket_end = content.find("\n    ]\n", start)
    if bracket_end == -1:
        return False

    new_content = content[:bracket_end] + "\n" + new_block + content[bracket_end:]
    return update_app_py(new_content, sha, f"🤖 Bot: Añadir vídeo {titulo}")

# ── Auth check ────────────────────────────────────────────────────────────────
def is_owner(update: Update):
    return update.effective_chat.id == OWNER_CHAT_ID

# ── Commands ──────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    msg = (
        "👋 *CRZ Trader Bot* — Panel de control\n\n"
        "📊 /analisis — Publicar nuevo análisis gráfico\n"
        "🎥 /video — Publicar nuevo vídeo de Zoom\n"
        "❌ /cancelar — Cancelar operación actual\n"
        "ℹ️ /estado — Ver estado de la app"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def analisis_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    session.update({"mode": "analisis", "semana": None, "activo": None,
                    "texto": None, "imagen": None, "audio": None})

    keyboard = [
        [InlineKeyboardButton("📈 NAS100", callback_data="activo_NAS100"),
         InlineKeyboardButton("📈 SP500",  callback_data="activo_SP500")],
        [InlineKeyboardButton("🥇 XAU",   callback_data="activo_XAU"),
         InlineKeyboardButton("🥈 XAG",   callback_data="activo_XAG")],
    ]
    await update.message.reply_text(
        "📊 *Nuevo análisis*\n\n¿Qué activo vas a analizar?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def video_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    session.update({"mode": "video", "semana": None, "texto": None})
    await update.message.reply_text(
        "🎥 *Nuevo vídeo de análisis*\n\n"
        "Envía el enlace de Zoom y el código en este formato:\n\n"
        "`https://zoom.us/rec/... | CODIGO`",
        parse_mode="Markdown"
    )

async def cancelar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    session.update({"mode": None})
    await update.message.reply_text("❌ Operación cancelada.")

async def estado_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    await update.message.reply_text(
        "📡 *Estado de la app*\n\n"
        "🌐 [Abrir app](https://mt5-analyzer-crz.streamlit.app)\n"
        "📁 [Ver GitHub](https://github.com/cristianzafra924-source/mt5-analyzer)",
        parse_mode="Markdown"
    )

# ── Callbacks ─────────────────────────────────────────────────────────────────
async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("activo_"):
        activo = query.data.replace("activo_", "")
        session["activo"] = activo
        await query.edit_message_text(
            f"✅ Activo: *{activo}*\n\n"
            f"Ahora escribe la semana, por ejemplo:\n`Semana 15 · Abril 2026`",
            parse_mode="Markdown"
        )

# ── Messages ──────────────────────────────────────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    text = update.message.text.strip()
    mode = session.get("mode")

    if mode == "analisis":
        if not session.get("activo"):
            await update.message.reply_text("Primero usa /analisis y selecciona el activo.")
            return

        if not session.get("semana"):
            session["semana"] = text
            await update.message.reply_text(
                f"✅ Semana: *{text}*\n\nAhora escribe el texto del análisis:",
                parse_mode="Markdown"
            )
        elif not session.get("texto"):
            session["texto"] = text
            await update.message.reply_text(
                "✅ Texto guardado.\n\n📸 Ahora envía la *imagen* del gráfico:",
                parse_mode="Markdown"
            )

    elif mode == "video":
        if "|" in text:
            parts = text.split("|")
            url_video = parts[0].strip()
            codigo = parts[1].strip()
            fecha = datetime.now().strftime("%B %Y")
            titulo = f"Análisis Semanal · {fecha}"
            desc = "Revisión semanal de NAS100, SP500, XAU y XAG."

            await update.message.reply_text("⏳ Publicando vídeo en la app...")
            ok = add_video_to_app(titulo, fecha, url_video, codigo, desc)
            if ok:
                await update.message.reply_text(
                    f"✅ *Vídeo publicado correctamente*\n\n"
                    f"📅 {titulo}\n🔗 {url_video}\n🔑 {codigo}\n\n"
                    f"🌐 [Ver en la app](https://mt5-analyzer-crz.streamlit.app)",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Error al publicar. Inténtalo de nuevo.")
            session["mode"] = None
        else:
            await update.message.reply_text(
                "Formato incorrecto. Usa:\n`URL | CODIGO`",
                parse_mode="Markdown"
            )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    if session.get("mode") != "analisis": return
    if not session.get("texto"):
        await update.message.reply_text("Primero escribe el texto del análisis.")
        return

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    img_bytes = bytes(await file.download_as_bytearray())
    session["imagen"] = img_bytes
    session["imagen_nombre"] = f"{session['activo']}_{datetime.now().strftime('%Y%m%d')}.png"

    await update.message.reply_text(
        "✅ Imagen guardada.\n\n🎙️ Ahora envía la *nota de voz* o un archivo de audio:\n"
        "_(O escribe /publicar para publicar sin audio)_",
        parse_mode="Markdown"
    )

async def handle_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    if session.get("mode") != "analisis": return

    audio = update.message.voice or update.message.audio
    if not audio:
        return

    file = await ctx.bot.get_file(audio.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())
    session["audio"] = audio_bytes
    ext = "ogg" if update.message.voice else "mp3"
    session["audio_nombre"] = f"audio_{session['activo']}_{datetime.now().strftime('%Y%m%d')}.{ext}"

    await update.message.reply_text(
        "✅ Audio guardado.\n\nEscribe /publicar para subir todo a la app.",
        parse_mode="Markdown"
    )

async def publicar_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update): return
    if session.get("mode") != "analisis":
        await update.message.reply_text("No hay ningún análisis pendiente. Usa /analisis primero.")
        return

    # Check required fields
    if not all([session.get("activo"), session.get("semana"),
                session.get("texto"), session.get("imagen")]):
        missing = []
        if not session.get("activo"):  missing.append("activo")
        if not session.get("semana"):  missing.append("semana")
        if not session.get("texto"):   missing.append("texto")
        if not session.get("imagen"):  missing.append("imagen")
        await update.message.reply_text(f"❌ Faltan: {', '.join(missing)}")
        return

    await update.message.reply_text("⏳ Subiendo archivos a GitHub...")

    # Upload image
    img_ok = upload_file(
        session["imagen_nombre"],
        session["imagen"],
        f"📸 {session['activo']} {session['semana']}"
    )

    # Upload audio if exists
    audio_b64 = ""
    if session.get("audio"):
        upload_file(
            session["audio_nombre"],
            session["audio"],
            f"🎙️ Audio {session['activo']} {session['semana']}"
        )
        audio_b64 = base64.b64encode(session["audio"]).decode()

    img_b64 = base64.b64encode(session["imagen"]).decode()

    await update.message.reply_text("⏳ Actualizando la app...")

    ok = add_analisis_to_app(
        semana=session["semana"],
        activo=session["activo"],
        img_nombre=session["imagen_nombre"],
        audio_nombre=session["audio_nombre"] or "",
        texto=session["texto"],
        img_b64=img_b64,
        audio_b64=audio_b64
    )

    if ok:
        await update.message.reply_text(
            f"✅ *Análisis publicado correctamente*\n\n"
            f"📈 {session['activo']} · {session['semana']}\n"
            f"📝 {session['texto'][:80]}...\n\n"
            f"🌐 [Ver en la app](https://mt5-analyzer-crz.streamlit.app)\n"
            f"_(La app se actualiza en 1-2 min)_",
            parse_mode="Markdown"
        )
        session.update({"mode": None, "semana": None, "activo": None,
                        "texto": None, "imagen": None, "audio": None})
    else:
        await update.message.reply_text("❌ Error al actualizar la app. Inténtalo de nuevo.")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("video",    video_cmd))
    app.add_handler(CommandHandler("cancelar", cancelar_cmd))
    app.add_handler(CommandHandler("estado",   estado_cmd))
    app.add_handler(CommandHandler("publicar", publicar_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))

    print("🤖 CRZ Trader Bot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
