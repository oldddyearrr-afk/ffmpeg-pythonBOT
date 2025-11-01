
# bot_live_demo.py - مع استمرارية البث ووضع التحريك
import time
import subprocess
import asyncio
import json
import os
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from aiohttp import web

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "BOT_TOKEN": os.environ.get("BOT_TOKEN", ""),
    "YOUR_USER_ID": os.environ.get("YOUR_USER_ID", ""),
    "CHANNEL_ID": os.environ.get("CHANNEL_ID", ""),
    "SOURCE_URL": os.environ.get("SOURCE_URL", ""),
    "CLIP_SECONDS": 14,
    "SLEEP_BETWEEN": 2,
    "WATERMARK_TEXT": "@xl9rr",
    "WATERMARK_POSITION": "bottom-center",
    "WATERMARK_MODE": "scroll",
    "ADD_TIMESTAMP": False,
    "BUFFER_SIZE": 1
}

class ConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()
        self.lock = threading.Lock()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    return {**DEFAULT_CONFIG, **loaded}
            except:
                pass
        return DEFAULT_CONFIG.copy()

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        with self.lock:
            self.config[key] = value

config = ConfigManager(CONFIG_FILE)

required_vars = ["BOT_TOKEN", "YOUR_USER_ID", "CHANNEL_ID", "SOURCE_URL"]
missing_vars = [var for var in required_vars if not config.get(var)]

if missing_vars:
    print("❌ المتغيرات المطلوبة:")
    for var in missing_vars:
        print(f"   {var}")
    exit(1)

bot = Bot(token=config.get("BOT_TOKEN"))
clip_queue = Queue(maxsize=config.get("BUFFER_SIZE", 1))
stats = {"clips_sent": 0, "clips_failed": 0, "uptime_start": time.time()}
broadcast_running = False
active_users = []
stream_position = 0  # متتبع موضع البث

# تنظيف معرف القناة
channel_id = str(config.get("CHANNEL_ID")).strip()
if not channel_id.startswith("-100") and not channel_id.startswith("@"):
    if channel_id.startswith("-"):
        pass
    else:
        channel_id = f"-100{channel_id}"
    config.set("CHANNEL_ID", channel_id)

owner_id = str(config.get("YOUR_USER_ID"))
if owner_id not in active_users:
    active_users.append(owner_id)

print(f"👥 المشتركين: {len(active_users)}")
print(f"📺 القناة: {channel_id}")

# Web Server
async def handle_health(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    await site.start()
    print("🌐 http://0.0.0.0:5000")

# أوامر البوت
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id not in active_users:
        active_users.append(user_id)

    status = "🟢 يعمل" if broadcast_running else "🔴 متوقف"
    await update.message.reply_text(
        f"✅ أهلاً بك\n\n"
        f"البث: {status}\n"
        f"المشتركين: {len(active_users)}\n\n"
        f"/help - عرض الأوامر"
    )

async def startlive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    global broadcast_running, stream_position
    user_id = str(update.effective_user.id)

    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ للمالك فقط")
        return

    if broadcast_running:
        await update.message.reply_text("⚠️ البث يعمل")
        return

    broadcast_running = True
    stream_position = 0
    await update.message.reply_text("🎬 جاري بدء البث...")
    asyncio.create_task(broadcast_loop())
    await asyncio.sleep(2)
    await update.message.reply_text(
        f"✅ البث نشط\n"
        f"المشتركين: {len(active_users)}\n"
        f"المدة: {config.get('CLIP_SECONDS')}ث"
    )

async def stoplive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    global broadcast_running
    user_id = str(update.effective_user.id)

    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ للمالك فقط")
        return

    if not broadcast_running:
        await update.message.reply_text("⚠️ البث متوقف")
        return

    broadcast_running = False
    await update.message.reply_text("🛑 جاري الإيقاف...")
    await asyncio.sleep(2)
    await update.message.reply_text("✅ تم إيقاف البث")

async def watermark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ للمالك فقط")
        return

    if not context.args:
        await update.message.reply_text(
            f"العلامة: {config.get('WATERMARK_TEXT')}\n\n"
            "مثال: /watermark @username"
        )
        return

    new_text = " ".join(context.args)
    config.set("WATERMARK_TEXT", new_text)
    await update.message.reply_text(f"✅ تم تغيير العلامة إلى: {new_text}")

async def wpos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ للمالك فقط")
        return

    if not context.args:
        current = config.get('WATERMARK_POSITION')
        await update.message.reply_text(
            f"الموقع: {current}\n\n"
            "/wpos top-left ↖️\n"
            "/wpos bottom-center ↓"
        )
        return

    position = context.args[0].lower()
    if position not in ["top-left", "bottom-center"]:
        await update.message.reply_text("❌ اختر: top-left أو bottom-center")
        return

    config.set("WATERMARK_POSITION", position)
    await update.message.reply_text(f"✅ الموقع: {position}")

async def wmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ للمالك فقط")
        return

    if not context.args:
        current = config.get('WATERMARK_MODE')
        status = "🔄 متحرك" if current == "scroll" else "⏸️ ثابت"
        await update.message.reply_text(
            f"النمط: {status}\n\n"
            "/wmode scroll - متحرك من اليمين لليسار\n"
            "/wmode static - ثابت"
        )
        return

    mode = context.args[0].lower()
    if mode not in ["scroll", "static"]:
        await update.message.reply_text("❌ اختر: scroll أو static")
        return

    config.set("WATERMARK_MODE", mode)
    status = "🔄 متحرك من اليمين لليسار" if mode == "scroll" else "⏸️ ثابت"
    await update.message.reply_text(f"✅ النمط: {status}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        return

    uptime = time.time() - stats["uptime_start"]
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    status = "🟢 يعمل" if broadcast_running else "🔴 متوقف"
    mode = "🔄 متحرك" if config.get('WATERMARK_MODE') == "scroll" else "⏸️ ثابت"

    await update.message.reply_text(
        f"📊 الإحصائيات\n\n"
        f"البث: {status}\n"
        f"المشتركين: {len(active_users)}\n"
        f"المقاطع: {stats['clips_sent']}\n"
        f"فشل: {stats['clips_failed']}\n"
        f"الوقت: {hours}س {minutes}د\n\n"
        f"العلامة: {config.get('WATERMARK_TEXT')}\n"
        f"الموقع: {config.get('WATERMARK_POSITION')}\n"
        f"النمط: {mode}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    await update.message.reply_text(
        "📋 قائمة الأوامر\n\n"
        "للجميع:\n"
        "/start - بدء البوت\n"
        "/help - قائمة الأوامر\n\n"
        "للمالك فقط:\n"
        "/startLIVE - تشغيل البث 🟢\n"
        "/stopLIVE - إيقاف البث 🔴\n"
        "/watermark - تغيير النص\n"
        "/wpos - تغيير الموقع\n"
        "/wmode - نمط الحركة\n"
        "/stats - الإحصائيات\n\n"
        "المواقع المتاحة:\n"
        "top-left ↖️ أعلى اليسار\n"
        "bottom-center ↓ أسفل الوسط\n\n"
        "أنماط الحركة:\n"
        "scroll 🔄 متحرك من اليمين لليسار\n"
        "static ⏸️ ثابت"
    )

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    if user_id not in active_users:
        active_users.append(user_id)
        await update.message.reply_text("✅ تم تسجيلك في البث")
    else:
        await update.message.reply_text("✅ أنت مسجل")

# معالجة الفيديو
def get_watermark_position(position):
    positions = {
        "top-left": "x=10:y=10",
        "bottom-center": "x=(w-tw)/2:y=h-th-10"
    }
    return positions.get(position, "x=(w-tw)/2:y=h-th-10")

def build_ffmpeg_cmd(src, out, start_pos, duration, watermark_text="", watermark_position="bottom-center", watermark_mode="scroll"):
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-timeout", "10000000",
        "-ss", str(start_pos),
        "-i", src,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart"
    ]

    if watermark_text:
        escaped = watermark_text.replace(":", "\\:").replace("'", "\\'")
        
        if watermark_mode == "scroll":
            # حركة من اليمين لليسار بسرعة 125
            pos = f"x=w-125*t:y=h-th-20"
            filter_text = (
                f"drawtext=text='{escaped}':{pos}:"
                f"fontsize=40:fontcolor=white@1.0:"
                f"font='Arial Black':"
                f"borderw=3:bordercolor=black@1.0:"
                f"shadowcolor=black@0.8:shadowx=3:shadowy=3"
            )
        else:
            # ثابت
            pos = get_watermark_position(watermark_position)
            filter_text = (
                f"drawtext=text='{escaped}':{pos}:"
                f"fontsize=40:fontcolor=white@1.0:"
                f"font='Arial Black':"
                f"borderw=3:bordercolor=black@1.0:"
                f"shadowcolor=black@0.8:shadowx=3:shadowy=3"
            )
        
        cmd += ["-vf", filter_text]

    cmd.append(out)
    return cmd

def fetch_clip(output_path, start_position):
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except:
            pass

    cmd = build_ffmpeg_cmd(
        config.get("SOURCE_URL"),
        output_path,
        start_position,
        config.get("CLIP_SECONDS"),
        config.get("WATERMARK_TEXT", ""),
        config.get("WATERMARK_POSITION", "bottom-center"),
        config.get("WATERMARK_MODE", "scroll")
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            _, stderr = process.communicate(timeout=180)

            if process.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                if attempt < max_retries - 1:
                    time.sleep(5)

        except subprocess.TimeoutExpired:
            process.kill()
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(5)

    return False

async def send_clip(clip_path):
    if not os.path.exists(clip_path):
        return False

    success_count = 0

    # القناة
    try:
        with open(clip_path, "rb") as f:
            await bot.send_video(
                chat_id=config.get("CHANNEL_ID"),
                video=f,
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300
            )
        success_count += 1
        print("✅ القناة")
    except Exception as e:
        print(f"❌ القناة: {str(e)[:50]}")

    # المستخدمين
    for user_id in active_users:
        try:
            with open(clip_path, "rb") as f:
                await bot.send_video(
                    chat_id=user_id,
                    video=f,
                    supports_streaming=True,
                    read_timeout=300,
                    write_timeout=300
                )
            success_count += 1
        except:
            pass
        await asyncio.sleep(0.3)

    try:
        if os.path.exists(clip_path):
            os.remove(clip_path)
    except:
        pass

    stats["clips_sent"] += 1
    print(f"📊 {success_count}/{len(active_users) + 1}")
    return success_count > 0

async def send_start_message():
    try:
        await bot.send_message(
            chat_id=config.get("CHANNEL_ID"),
            text="🎬 البث المباشر بدأ"
        )
    except:
        pass

    for user_id in active_users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text="🎬 البث المباشر بدأ"
            )
        except:
            pass
        await asyncio.sleep(0.3)

def clip_producer():
    global stream_position
    clip_counter = 0
    consecutive_failures = 0

    while broadcast_running:
        try:
            clip_counter += 1
            output_path = f"/tmp/clip_{clip_counter}.mp4"

            print(f"🎬 مقطع #{clip_counter} (من {stream_position}ث)")
            success = fetch_clip(output_path, stream_position)

            if success and os.path.exists(output_path) and broadcast_running:
                clip_queue.put(output_path)
                print(f"✅ جاهز #{clip_counter}")
                stream_position += config.get("CLIP_SECONDS")
                consecutive_failures = 0
            else:
                stats["clips_failed"] += 1
                consecutive_failures += 1

                if consecutive_failures >= 10:
                    print("⏸️ انتظار 30ث")
                    stream_position = 0
                    consecutive_failures = 0
                    time.sleep(30)
                else:
                    time.sleep(10)

        except Exception:
            consecutive_failures += 1
            if consecutive_failures >= 10:
                stream_position = 0
                time.sleep(60)
                consecutive_failures = 0
            else:
                time.sleep(10)

async def clip_consumer():
    while broadcast_running:
        try:
            if not clip_queue.empty():
                clip_path = clip_queue.get()

                try:
                    await send_clip(clip_path)
                except Exception:
                    try:
                        if os.path.exists(clip_path):
                            os.remove(clip_path)
                    except:
                        pass

                sleep_time = config.get("SLEEP_BETWEEN", 0)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            else:
                await asyncio.sleep(0.5)
        except Exception:
            await asyncio.sleep(2)

async def broadcast_loop():
    print("🎬 جاري بدء البث...")
    await send_start_message()
    await asyncio.sleep(2)

    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, clip_producer)

    await clip_consumer()

async def main():
    asyncio.create_task(start_web_server())

    while True:
        try:
            application = Application.builder().token(config.get("BOT_TOKEN")).build()

            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("startLIVE", startlive_command))
            application.add_handler(CommandHandler("stopLIVE", stoplive_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("stats", stats_command))
            application.add_handler(CommandHandler("watermark", watermark_command))
            application.add_handler(CommandHandler("wpos", wpos_command))
            application.add_handler(CommandHandler("wmode", wmode_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

            await application.initialize()
            await application.start()

            if application.updater:
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES
                )

            print("✅ البوت يعمل")
            print("⏸️ استخدم /startLIVE للبدء")

            await asyncio.Event().wait()

        except Exception as e:
            print(f"🚨 خطأ: {str(e)[:100]}")
            print("🔄 إعادة المحاولة بعد 30ث")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
