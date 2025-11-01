# bot_live_demo.py - Enhanced Version with Dynamic Watermark + Web Server
import time
import subprocess
import asyncio
import json
import os
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from aiohttp import web

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "BOT_TOKEN": "7810330489:AAEyFvyXZuxAwLAubhLEnY6QTg-shHJbx-0",
    "YOUR_USER_ID": "5747051433",
    "CHANNEL_ID": "-1002803181805",
    "SOURCE_URL": "http://g.rosexz.xyz/at/sh/805768?token=SxAKVEBaQ14XUwYBBVYCD1VdBQRSB1cABAAEUVoFBw4JC1ADBQZUAVQTHBNGEEFcBQhpWAASCFcBAABTFUQTR0NXEGpaVkNeFwUHBgxVBAxGSRRFDV1XQA8ABlQKUFcFCAdXGRFCCAAXC15EWQgfGwEdQlQWXlMOalVUElAFAxQKXBdZXx5DC1tuVFRYBV1dRl8UAEYcEAtGQRNeVxMKWhwQAFxHQAAQUBMKX0AIXxVGBllECkRAGxcLEy1oREoUVUoWUF1BCAtbEwoTQRcRFUYMRW4WVUEWR1RQCVwURAwSAkAZEV8AHGpSX19bAVBNDQpYQkYKEFMXHRMJVggPQl9APUVaVkNeW0RcXUg",
    "CLIP_SECONDS": 12,
    "SLEEP_BETWEEN": 0,
    "VIDEO_BITRATE": "3000k",
    "AUDIO_BITRATE": "128k",
    "CRF": "22",
    "WATERMARK_TEXT": "@xl9rr",
    "WATERMARK_MODE": "static",
    "WATERMARK_POSITION": "top-left",
    "ADD_TIMESTAMP": True,
    "BUFFER_SIZE": 3
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

    def reload(self):
        self.config = self.load_config()
        return self.config

config = ConfigManager(CONFIG_FILE)
bot = Bot(token=config.get("BOT_TOKEN"))

clip_queue = Queue(maxsize=config.get("BUFFER_SIZE", 3))
stats = {"clips_sent": 0, "clips_failed": 0, "uptime_start": time.time()}

broadcast_running = False
broadcast_task = None

active_users = [config.get("YOUR_USER_ID")]
print(f"📋 عدد المستخدمين: {len(active_users)}")
print(f"👥 المستخدمين: {active_users}")
print(f"📺 القناة: {config.get('CHANNEL_ID')}")

async def handle_health(request):
    return web.Response(text="OK", content_type="text/plain")

async def handle_root(request):
    return web.Response(text="", content_type="text/html")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/health', handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    await site.start()
    print("🌐 Web server running on http://0.0.0.0:5000")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "مجهول"

    if user_id not in active_users:
        active_users.append(user_id)
        print(f"✅ مستخدم جديد: {username} ({user_id})")

    broadcast_status = "🟢 يعمل" if broadcast_running else "🔴 متوقف"

    await update.message.reply_text(
        "🎬 مرحباً بك في بوت البث المباشر!\n\n"
        "✅ تم تسجيلك بنجاح\n"
        f"📺 حالة البث: {broadcast_status}\n\n"
        f"👤 عدد المشتركين: {len(active_users)}\n\n"
        "📖 اكتب /help لعرض جميع الأوامر المتاحة"
    )

async def startlive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global broadcast_running

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if broadcast_running:
        await update.message.reply_text("⚠️ البث يعمل بالفعل!\n\nاستخدم /stopLIVE لإيقافه أولاً")
        return

    broadcast_running = True
    await update.message.reply_text("🎬 جاري بدء البث المباشر...")

    asyncio.create_task(broadcast_loop())

    await asyncio.sleep(2)
    await update.message.reply_text(
        "✅ تم بدء البث المباشر بنجاح!\n\n"
        f"📺 المشتركين: {len(active_users)}\n"
        f"🎬 مدة المقطع: {config.get('CLIP_SECONDS')}ث\n"
        f"🎨 العلامة: {config.get('WATERMARK_TEXT')}"
    )

async def stoplive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global broadcast_running

    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not broadcast_running:
        await update.message.reply_text("⚠️ البث متوقف بالفعل!")
        return

    broadcast_running = False
    await update.message.reply_text("🛑 جاري إيقاف البث...")

    await asyncio.sleep(2)
    await update.message.reply_text(
        "✅ تم إيقاف البث المباشر!\n\n"
        "استخدم /startLIVE لبدء البث مجدداً"
    )

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "مجهول"

    if user_id not in active_users:
        active_users.append(user_id)
        print(f"✅ مستخدم جديد عبر رسالة: {username} ({user_id})")
        await update.message.reply_text(
            "✅ تم تسجيلك تلقائياً!\n"
            "📺 سوف تستقبل البث المباشر"
        )
    else:
        await update.message.reply_text("👍 أنت مسجل بالفعل!")

async def watermark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not context.args:
        await update.message.reply_text(
            f"📝 النص الحالي: {config.get('WATERMARK_TEXT')}\n\n"
            "استخدم: /watermark النص الجديد"
        )
        return

    new_text = " ".join(context.args)
    config.set("WATERMARK_TEXT", new_text)

    await update.message.reply_text(f"✅ تم تغيير العلامة المائية إلى:\n{new_text}")

async def wmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not context.args:
        current = config.get('WATERMARK_MODE')
        await update.message.reply_text(
            f"🎬 النمط الحالي: `{current}`\n\n"
            "🎨 **الأنماط المتاحة:**\n\n"
            "• `/wmode static` - ثابت 📌\n"
            "• `/wmode scroll` - يتحرك ← 🏃\n"
            "• `/wmode bounce` - يرتد ↔️ 🎾\n"
            "• `/wmode fade` - ظهور واختفاء 💫\n"
            "• `/wmode pulse` - نبض 💓\n\n"
            "⚙️ **سرعة الحركة:**\n"
            "• `/wspeed 50` - للتحكم بسرعة scroll/bounce",
            parse_mode="Markdown"
        )
        return

    mode = context.args[0].lower()

    valid_modes = ["static", "scroll", "bounce", "fade", "pulse"]
    
    if mode not in valid_modes:
        await update.message.reply_text(
            f"❌ نمط غير صحيح!\n\n"
            f"استخدم: {', '.join(valid_modes)}",
            parse_mode="Markdown"
        )
        return

    config.set("WATERMARK_MODE", mode)

    icons = {"static": "📌", "scroll": "🏃", "bounce": "🎾", "fade": "💫", "pulse": "💓"}
    await update.message.reply_text(
        f"✅ تم تغيير نمط الحركة!\n\n"
        f"{icons.get(mode, '')} النمط الجديد: `{mode}`",
        parse_mode="Markdown"
    )

async def wpos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not context.args:
        current = config.get('WATERMARK_POSITION')
        await update.message.reply_text(
            f"📍 الموقع الحالي: `{current}`\n\n"
            "🎯 **المواقع المسبقة:**\n"
            "• `top-left`, `top-center`, `top-right` ↖️↑↗️\n"
            "• `center-left`, `center`, `center-right` ←🎯→\n"
            "• `bottom-left`, `bottom-center`, `bottom-right` ↙️↓↘️\n\n"
            "📐 **إحداثيات مخصصة:**\n"
            "• `/wpos x:100,y:50` - بالبيكسل\n"
            "• `/wpos x:10%,y:20%` - بالنسبة المئوية\n"
            "• `/wpos x:w-100,y:h-50` - نسبة للعرض/الارتفاع\n"
            "• `/wpos x:50%,y:h-100` - مزيج\n\n"
            "💡 **أمثلة:**\n"
            "• `x:20,y:30` → 20 بيكسل من اليسار، 30 من الأعلى\n"
            "• `x:50%,y:50%` → منتصف الشاشة\n"
            "• `x:w-150,y:100` → 150 بيكسل من اليمين",
            parse_mode="Markdown"
        )
        return

    position = " ".join(context.args)

    config.set("WATERMARK_POSITION", position)

    presets = {
        "top-left": "↖️", "top-center": "↑", "top-right": "↗️",
        "center-left": "←", "center": "🎯", "center-right": "→",
        "bottom-left": "↙️", "bottom-center": "↓", "bottom-right": "↘️"
    }

    icon = presets.get(position, "📍")
    
    # شرح الموقع
    explanation = ""
    if position == "center":
        explanation = "\n(منتصف الشاشة تماماً)"
    elif "custom" in position or ("x:" in position and "y:" in position):
        explanation = f"\n(إحداثيات مخصصة)"
    
    await update.message.reply_text(
        f"✅ تم تعيين الموقع!{explanation}\n\n"
        f"{icon} الموقع: `{position}`\n\n"
        f"💡 سيظهر في المقطع التالي",
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        return

    uptime = time.time() - stats["uptime_start"]
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)

    broadcast_status = "🟢 يعمل" if broadcast_running else "🔴 متوقف"

    msg = f"📊 إحصائيات البوت:\n\n"
    msg += f"📡 حالة البث: {broadcast_status}\n"
    msg += f"👥 عدد المشتركين: {len(active_users)}\n"
    msg += f"✅ مقاطع مرسلة: {stats['clips_sent']}\n"
    msg += f"❌ مقاطع فشلت: {stats['clips_failed']}\n"
    msg += f"⏱️ وقت التشغيل: {hours}س {minutes}د\n"
    msg += f"🎬 المصدر: {config.get('SOURCE_URL')[:50]}...\n"
    msg += f"⚙️ مدة المقطع: {config.get('CLIP_SECONDS')}ث\n\n"
    msg += f"🎨 العلامة المائية:\n"
    msg += f"   النص: {config.get('WATERMARK_TEXT')}\n"
    msg += f"   النمط: {config.get('WATERMARK_MODE')}\n"
    msg += f"   الموقع: {config.get('WATERMARK_POSITION')}"

    await update.message.reply_text(msg)

async def wspeed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not context.args:
        scroll_speed = config.get("WATERMARK_SCROLL_SPEED", 50)
        bounce_speed = config.get("WATERMARK_BOUNCE_SPEED", 100)
        await update.message.reply_text(
            f"⚡ **السرعة الحالية:**\n\n"
            f"🏃 Scroll: {scroll_speed}\n"
            f"🎾 Bounce: {bounce_speed}\n\n"
            f"استخدم: `/wspeed رقم` (10-200)",
            parse_mode="Markdown"
        )
        return

    try:
        speed = int(context.args[0])
        if speed < 10 or speed > 200:
            await update.message.reply_text("⚠️ السرعة يجب أن تكون بين 10 و 200")
            return
        
        config.set("WATERMARK_SCROLL_SPEED", speed)
        config.set("WATERMARK_BOUNCE_SPEED", speed)
        
        await update.message.reply_text(f"✅ تم تعيين السرعة إلى: {speed}")
    except:
        await update.message.reply_text("❌ يجب إدخال رقم صحيح!")

async def wstyle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        await update.message.reply_text("❌ هذا الأمر للمالك فقط")
        return

    if not context.args:
        size = config.get("WATERMARK_FONTSIZE", 28)
        color = config.get("WATERMARK_COLOR", "white")
        border = config.get("WATERMARK_BORDER", 2)
        opacity = config.get("WATERMARK_OPACITY", 1.0)
        
        await update.message.reply_text(
            f"🎨 **التنسيق الحالي:**\n\n"
            f"📏 الحجم: {size}\n"
            f"🎨 اللون: {color}\n"
            f"🖼️ الحدود: {border}px\n"
            f"👁️ الشفافية: {opacity}\n\n"
            f"**أمثلة:**\n"
            f"• `/wstyle size 36` - حجم الخط\n"
            f"• `/wstyle color red` - اللون\n"
            f"• `/wstyle border 3` - عرض الحدود\n"
            f"• `/wstyle opacity 0.8` - الشفافية (0-1)",
            parse_mode="Markdown"
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ استخدم: `/wstyle [size/color/border/opacity] القيمة`", parse_mode="Markdown")
        return

    prop = context.args[0].lower()
    value = context.args[1]

    try:
        if prop == "size":
            config.set("WATERMARK_FONTSIZE", int(value))
            await update.message.reply_text(f"✅ حجم الخط: {value}")
        elif prop == "color":
            config.set("WATERMARK_COLOR", value)
            await update.message.reply_text(f"✅ اللون: {value}")
        elif prop == "border":
            config.set("WATERMARK_BORDER", int(value))
            await update.message.reply_text(f"✅ عرض الحدود: {value}px")
        elif prop == "opacity":
            opacity = float(value)
            if 0 <= opacity <= 1:
                config.set("WATERMARK_OPACITY", opacity)
                await update.message.reply_text(f"✅ الشفافية: {opacity}")
            else:
                await update.message.reply_text("⚠️ الشفافية يجب أن تكون بين 0 و 1")
        else:
            await update.message.reply_text("❌ خاصية غير صحيحة! استخدم: size, color, border, opacity")
    except:
        await update.message.reply_text("❌ قيمة غير صحيحة!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🎬 **دليل استخدام البوت**

📌 **الأوامر العامة:**
• `/start` - بدء استخدام البوت والتسجيل
• `/help` - عرض هذه القائمة

📊 **أوامر المالك فقط:**

**التحكم بالبث:**
• `/startLIVE` - 🟢 بدء البث المباشر
• `/stopLIVE` - 🔴 إيقاف البث المباشر

**إدارة العلامة المائية - محسّنة:**
• `/watermark النص` - تغيير النص
• `/wmode النمط` - static/scroll/bounce/fade/pulse
• `/wpos الموقع` - مواقع مسبقة أو إحداثيات مخصصة
• `/wspeed الرقم` - سرعة الحركة (10-200)
• `/wstyle الخاصية القيمة` - التنسيق (size/color/border/opacity)

**أمثلة على المواقع:**
• `/wpos center` - منتصف الشاشة
• `/wpos x:100,y:50` - 100 بيكسل من اليسار، 50 من الأعلى
• `/wpos x:50%,y:h-100` - منتصف العرض، 100 من الأسفل

**أوامر أخرى:**
• `/stats` - عرض إحصائيات البوت
• `/reload` - إعادة تحميل الإعدادات

💡 **نصائح:**
- جميع التغييرات تطبق فوراً على المقاطع الجديدة
- يمكنك تغيير الإعدادات أثناء البث

✨ البوت الآن أكثر مرونة وديناميكية!
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != config.get("YOUR_USER_ID"):
        return

    config.reload()
    await update.message.reply_text("✅ تم إعادة تحميل الإعدادات من config.json")

def parse_custom_position(position):
    """
    دعم المواقع المخصصة:
    - top-left, center, etc. (مسبقة)
    - x:100,y:50 (بالبيكسل)
    - x:10%,y:20% (بالنسبة المئوية)
    - x:w-100,y:h-50 (نسبة للعرض/الارتفاع)
    """
    presets = {
        "top-left": "x=10:y=10",
        "top-right": "x=w-tw-10:y=10",
        "bottom-left": "x=10:y=h-th-10",
        "bottom-right": "x=w-tw-10:y=h-th-10",
        "bottom-center": "x=(w-tw)/2:y=h-th-10",
        "center": "x=(w-tw)/2:y=(h-th)/2",
        "top-center": "x=(w-tw)/2:y=10",
        "center-left": "x=10:y=(h-th)/2",
        "center-right": "x=w-tw-10:y=(h-th)/2"
    }
    
    if position in presets:
        return presets[position]
    
    # تحليل الإحداثيات المخصصة
    try:
        parts = position.lower().replace(" ", "").split(",")
        x_part = None
        y_part = None
        
        for part in parts:
            if part.startswith("x:"):
                x_val = part.split(":", 1)[1]
                if "%" in x_val:
                    percent = float(x_val.replace("%", ""))
                    x_part = f"w*{percent/100}"
                elif "w-" in x_val:
                    offset = x_val.replace("w-", "")
                    x_part = f"w-{offset}"
                elif "w+" in x_val:
                    offset = x_val.replace("w+", "")
                    x_part = f"w+{offset}"
                else:
                    x_part = x_val
                    
            elif part.startswith("y:"):
                y_val = part.split(":", 1)[1]
                if "%" in y_val:
                    percent = float(y_val.replace("%", ""))
                    y_part = f"h*{percent/100}"
                elif "h-" in y_val:
                    offset = y_val.replace("h-", "")
                    y_part = f"h-{offset}"
                elif "h+" in y_val:
                    offset = y_val.replace("h+", "")
                    y_part = f"h+{offset}"
                else:
                    y_part = y_val
        
        if x_part and y_part:
            return f"x={x_part}:y={y_part}"
    except:
        pass
    
    return "x=10:y=10"

def build_ffmpeg_cmd_with_watermark(src, out, duration, v_bitrate, a_bitrate, crf_value, watermark_text="", watermark_mode="static", watermark_position="top-left", add_timestamp=False):
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-timeout", "10000000",
        "-i", src,
        "-t", str(duration)
    ]

    filters = []

    if watermark_text:
        escaped_text = watermark_text.replace(":", "\\:").replace("'", "\\'")
        pos = parse_custom_position(watermark_position)
        
        # استخراج إعدادات إضافية من config
        font_size = config.get("WATERMARK_FONTSIZE", 28)
        font_color = config.get("WATERMARK_COLOR", "white")
        border_width = config.get("WATERMARK_BORDER", 2)
        border_color = config.get("WATERMARK_BORDER_COLOR", "black")
        opacity = config.get("WATERMARK_OPACITY", 1.0)

        # إعدادات الخط الأساسية
        base_font = f"fontcolor={font_color}@{opacity}:borderw={border_width}:bordercolor={border_color}:shadowcolor=black@0.7:shadowx=2:shadowy=2"

        if watermark_mode == "static":
            filters.append(f"drawtext=text='{escaped_text}':{pos}:fontsize={font_size}:{base_font}")

        elif watermark_mode == "scroll":
            speed = config.get("WATERMARK_SCROLL_SPEED", 50)
            # استخراج y من الموقع أو استخدام 10 كقيمة افتراضية
            y_pos = "10"
            if watermark_position == "center":
                y_pos = "(h-th)/2"
            elif "bottom" in watermark_position:
                y_pos = "h-th-10"
            filters.append(f"drawtext=text='{escaped_text}':x='w-mod(t*{speed},w+tw)':y={y_pos}:fontsize={font_size}:{base_font}")

        elif watermark_mode == "bounce":
            speed = config.get("WATERMARK_BOUNCE_SPEED", 100)
            y_pos = "10"
            if watermark_position == "center":
                y_pos = "(h-th)/2"
            elif "bottom" in watermark_position:
                y_pos = "h-th-10"
            filters.append(f"drawtext=text='{escaped_text}':x='if(lt(mod(t,4),2),10+mod(t*{speed},w-tw-20),w-tw-10-mod(t*{speed},w-tw-20))':y={y_pos}:fontsize={font_size}:{base_font}")
        
        elif watermark_mode == "fade":
            filters.append(f"drawtext=text='{escaped_text}':{pos}:fontsize={font_size}:{base_font}:alpha='if(lt(mod(t,4),2),mod(t,2),2-mod(t,2))'")
        
        elif watermark_mode == "pulse":
            # استخدام حجم ديناميكي مع الحفاظ على الموقع
            filters.append(f"drawtext=text='{escaped_text}':{pos}:fontsize='{font_size}+sin(t*2)*5':{base_font}")

    if add_timestamp:
        filters.append("drawtext=text='%{localtime\\:%H\\\\\\:%M\\\\\\:%S}':x=w-tw-10:y=h-th-10:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.5")

    if filters:
        filter_str = ",".join(filters)
        cmd += ["-vf", filter_str]

    if crf_value:
        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", str(crf_value),
            "-c:a", "aac",
            "-b:a", a_bitrate,
            "-movflags", "+faststart",
            out
        ]
    else:
        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-b:v", v_bitrate,
            "-maxrate", v_bitrate,
            "-bufsize", "2M",
            "-c:a", "aac",
            "-b:a", a_bitrate,
            "-movflags", "+faststart",
            out
        ]
    return cmd

def fetch_and_encode_clip(output_path):
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except:
            pass

    cmd = build_ffmpeg_cmd_with_watermark(
        config.get("SOURCE_URL"),
        output_path,
        config.get("CLIP_SECONDS"),
        config.get("VIDEO_BITRATE"),
        config.get("AUDIO_BITRATE"),
        config.get("CRF"),
        config.get("WATERMARK_TEXT", ""),
        config.get("WATERMARK_MODE", "static"),
        config.get("WATERMARK_POSITION", "top-left"),
        config.get("ADD_TIMESTAMP", True)
    )

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        return True
    except subprocess.TimeoutExpired:
        print(f"⏱️ انتهى الوقت - يُعاد المحاولة...")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ خطأ ffmpeg:", e.stderr.decode(errors="ignore") if e.stderr else str(e))
        return False
    except Exception as e:
        print(f"❌ خطأ غير متوقع:", str(e))
        return False

async def send_clip_to_users(clip_path):
    if not os.path.exists(clip_path):
        print("No output file to send.")
        return False

    success_count = 0

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
        print(f"✅ تم الإرسال للقناة")
    except Exception as e:
        print(f"❌ خطأ في القناة: {e}")

    tasks = []
    for user_id in active_users:
        tasks.append(send_to_user(user_id, clip_path))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count += sum(1 for r in results if r is True)

    try:
        os.remove(clip_path)
    except:
        pass

    stats["clips_sent"] += 1

    print(f"📊 نتيجة الإرسال: {success_count}/{len(active_users) + 1}")
    return success_count > 0

async def send_to_user(user_id, clip_path):
    try:
        with open(clip_path, "rb") as f:
            await bot.send_video(
                chat_id=user_id,
                video=f,
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300
            )
        print(f"✅ إرسال: {user_id}")
        return True
    except Exception as e:
        print(f"❌ خطأ: {user_id}")
        return False

async def send_start_broadcast_message():
    print("📢 إرسال إشعار بدء البث...")

    try:
        await bot.send_message(
            chat_id=config.get("CHANNEL_ID"),
            text="🎬 بدأ البث المباشر الآن!\n📺 كل مقطع يبدأ من نهاية المقطع السابق - لن تفوتك أي لحظة!"
        )
        print(f"✅ إشعار للقناة")
    except Exception as e:
        print(f"❌ خطأ إشعار القناة: {e}")

    for user_id in active_users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text="🎬 بدأ البث المباشر الآن!\n📺 كل مقطع يبدأ من نهاية المقطع السابق - لن تفوتك أي لحظة!"
            )
        except:
            pass
        await asyncio.sleep(0.3)

def clip_producer():
    clip_counter = 0
    clip_duration = config.get("CLIP_SECONDS")

    print(f"⚙️ إعدادات التسجيل:")
    print(f"   مدة المقطع: {clip_duration}ث")
    print(f"   بدون تداخل - كل مقطع يبدأ من نهاية السابق")
    print(f"   إعادة محاولة تلقائية عند الفشل")
    print(f"🎬 التسجيل المتتالي نشط - لن تفوت أي لحظة!\n")

    while broadcast_running:
        clip_counter += 1
        output_path = f"/tmp/clip_{clip_counter}.mp4"

        max_retries = 3
        retry_count = 0
        success = False

        while retry_count < max_retries and not success and broadcast_running:
            if retry_count > 0:
                print(f"🔄 محاولة {retry_count + 1}/{max_retries} للمقطع #{clip_counter}...")
            else:
                print(f"🎬 تسجيل مقطع #{clip_counter}...")

            success = fetch_and_encode_clip(output_path)

            if not success:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 3 * retry_count
                    print(f"⏳ انتظار {wait_time}ث قبل المحاولة التالية...")
                    time.sleep(wait_time)

        if success and os.path.exists(output_path) and broadcast_running:
            clip_queue.put(output_path)
            print(f"✅ مقطع #{clip_counter} جاهز في الطابور")
        else:
            stats["clips_failed"] += 1
            if broadcast_running:
                print(f"❌ فشل المقطع #{clip_counter} بعد {max_retries} محاولات")
                time.sleep(10)

async def clip_consumer():
    while broadcast_running:
        if not clip_queue.empty():
            clip_path = clip_queue.get()
            await send_clip_to_users(clip_path)

            sleep_time = config.get("SLEEP_BETWEEN", 0)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(0.5)

async def broadcast_loop():
    print("🎬 بدء البث المباشر...")

    await send_start_broadcast_message()
    await asyncio.sleep(2)

    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, clip_producer)

    await clip_consumer()

async def main():
    asyncio.create_task(start_web_server())

    application = Application.builder().token(config.get("BOT_TOKEN")).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("startLIVE", startlive_command))
    application.add_handler(CommandHandler("stopLIVE", stoplive_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("reload", reload_command))
    application.add_handler(CommandHandler("watermark", watermark_command))
    application.add_handler(CommandHandler("wmode", wmode_command))
    application.add_handler(CommandHandler("wpos", wpos_command))
    application.add_handler(CommandHandler("wspeed", wspeed_command))
    application.add_handler(CommandHandler("wstyle", wstyle_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    print("✅ البوت يعمل الآن ويستقبل الرسائل...")
    print("🌐 صفحة الويب: http://0.0.0.0:5000")
    print("⏸️  البث متوقف - استخدم /startLIVE لبدء البث")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
