import os
import logging
import tempfile
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8192774962:AAGYfF3nSUvUil3DT3qKfXpB7O6H5FGqNSo"

# Store user choices
user_choices = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎥 Video Emoji (100x100)", callback_data="emoji")],
        [InlineKeyboardButton("🖼️ Video Sticker (512x512)", callback_data="sticker")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 Telegram Video Converter Bot\n\n"
        "Choose what you want to create:\n\n"
        "🎥 **Video Emoji**: 100x100 pixels, no audio, max 3s\n"
        "🖼️ **Video Sticker**: 512x512 pixels, no audio, max 3s\n\n"
        "Both produce WebM files that work perfectly in Telegram!",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 **How to use:**
1. Click a button below to choose type
2. Send me your video file
3. I'll convert it automatically!

🎥 **Video Emoji Requirements:**
• WebM VP9 format
• 100x100 pixels
• No audio
• Max 3 seconds
• Max 256KB

🖼️ **Video Sticker Requirements:**
• WebM VP9 format  
• 512x512 pixels
• No audio (required for stickers)
• Max 3 seconds
• Max 256KB
• Supports transparency (alpha channel)

⚡ Both formats work perfectly in Telegram!

💡 **For transparent stickers:**
Use videos with transparent background (like MOV with alpha channel)
"""
    
    keyboard = [
        [InlineKeyboardButton("🎥 Video Emoji", callback_data="emoji")],
        [InlineKeyboardButton("🖼️ Video Sticker", callback_data="sticker")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    choice = query.data
    
    user_choices[user_id] = choice
    
    if choice == "emoji":
        await query.edit_message_text(
            "✅ Selected: 🎥 Video Emoji (100x100)\n\n"
            "Now send me your video! I'll convert it to:\n"
            "• WebM VP9 format\n• 100x100 pixels\n• No audio\n• Max 3 seconds\n• Under 256KB"
        )
    else:
        await query.edit_message_text(
            "✅ Selected: 🖼️ Video Sticker (512x512)\n\n"
            "Now send me your video! I'll convert it to:\n"
            "• WebM VP9 format\n• 512x512 pixels\n• No audio (required)\n• Max 3 seconds\n• Under 256KB\n• With transparency support\n\n"
            "💡 For best results, use a video with transparent background (like MOV with alpha channel)"
        )

async def convert_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert video based on user's choice"""
    user_id = update.message.from_user.id
    
    # Check if user has made a choice
    if user_id not in user_choices:
        keyboard = [
            [InlineKeyboardButton("🎥 Video Emoji", callback_data="emoji")],
            [InlineKeyboardButton("🖼️ Video Sticker", callback_data="sticker")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please choose what you want to create first:",
            reply_markup=reply_markup
        )
        return

    choice = user_choices[user_id]
    
    try:
        # Get the video file
        if update.message.video:
            file = await update.message.video.get_file()
            file_size = update.message.video.file_size
        elif update.message.document:
            # Check if it's a video file
            mime_type = update.message.document.mime_type or ""
            document_name = update.message.document.file_name or ""
            
            if not any(x in mime_type for x in ['video', 'mp4', 'mov', 'webm', 'quicktime']) and not any(x in document_name.lower() for x in ['.mp4', '.mov', '.avi', '.mkv', '.webm']):
                await update.message.reply_text("❌ Please send a video file (MP4, MOV, WebM, etc.)")
                return
                
            file = await update.message.document.get_file()
            file_size = update.message.document.file_size
        else:
            await update.message.reply_text("❌ Please send a video file")
            return

        # Check file size
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text("❌ File too large! Max 50MB")
            return

        processing_msg = await update.message.reply_text("📥 Downloading video...")

        # Create temp files
        with tempfile.NamedTemporaryFile(suffix='.input', delete=False) as infile:
            input_path = infile.name
        
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as outfile:
            output_path = outfile.name

        # Download video
        await file.download_to_drive(input_path)
        
        if os.path.getsize(input_path) == 0:
            await processing_msg.edit_text("❌ Download failed")
            return

        conversion_type = "Video Emoji" if choice == "emoji" else "Video Sticker"
        resolution = "100:100" if choice == "emoji" else "512:512"
        
        await processing_msg.edit_text(f"🔄 Converting to {conversion_type}...")

        # Different FFmpeg commands based on choice
        if choice == "emoji":
            # For emoji - standard conversion
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libvpx-vp9',
                '-b:v', '0',
                '-crf', '30',
                '-deadline', 'good',
                '-vf', f'scale={resolution}:force_original_aspect_ratio=disable,format=yuv420p',
                '-t', '3.0',
                '-an',
                '-row-mt', '1',
                '-threads', '0',
                '-y',
                output_path
            ]
        else:
            # For sticker - try to preserve transparency
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libvpx-vp9',
                '-b:v', '0',
                '-crf', '30',
                '-deadline', 'good',
                '-vf', f'scale={resolution}:force_original_aspect_ratio=disable,format=yuva420p',
                '-t', '3.0',
                '-an',
                '-auto-alt-ref', '0',
                '-row-mt', '1',
                '-threads', '0',
                '-y',
                output_path
            ]

        # Run FFmpeg
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for conversion
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            success = process.returncode == 0
            
        except asyncio.TimeoutError:
            await processing_msg.edit_text("❌ Conversion timed out")
            success = False

        # Check if conversion succeeded
        if not success:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"FFmpeg error: {error_msg}")
            
            # If sticker conversion failed, try without transparency
            if choice == "sticker":
                await processing_msg.edit_text("🔄 Retrying without transparency...")
                
                ffmpeg_retry_cmd = [
                    'ffmpeg',
                    '-i', input_path,
                    '-c:v', 'libvpx-vp9',
                    '-b:v', '0',
                    '-crf', '30',
                    '-deadline', 'good',
                    '-vf', f'scale={resolution}:force_original_aspect_ratio=disable,format=yuv420p',
                    '-t', '3.0',
                    '-an',
                    '-row-mt', '1',
                    '-threads', '0',
                    '-y',
                    output_path
                ]
                
                process_retry = await asyncio.create_subprocess_exec(
                    *ffmpeg_retry_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(process_retry.communicate(), timeout=30.0)
                    success = process_retry.returncode == 0
                    if not success:
                        await processing_msg.edit_text("❌ Conversion failed. Try a different video.")
                        return
                except asyncio.TimeoutError:
                    await processing_msg.edit_text("❌ Conversion timed out")
                    return
            else:
                await processing_msg.edit_text("❌ Conversion failed. Try a different video.")
                return

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            await processing_msg.edit_text("❌ No output file created")
            return

        # Check size limit (256KB)
        output_size = os.path.getsize(output_path)
        if output_size > 256 * 1024:
            # Try more aggressive compression
            await processing_msg.edit_text("📦 File too large, optimizing...")
            
            ffmpeg_compress_cmd = [
                'ffmpeg',
                '-i', output_path,
                '-c:v', 'libvpx-vp9',
                '-b:v', '0',
                '-crf', '40',
                '-deadline', 'realtime',
                '-an',
                '-row-mt', '1',
                '-threads', '0',
                '-y',
                output_path + '_compressed.webm'
            ]
            
            process_compress = await asyncio.create_subprocess_exec(
                *ffmpeg_compress_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process_compress.communicate(), timeout=20.0)
                if process_compress.returncode == 0 and os.path.exists(output_path + '_compressed.webm'):
                    os.replace(output_path + '_compressed.webm', output_path)
                    output_size = os.path.getsize(output_path)
            except:
                pass

        # Final size check
        if output_size > 256 * 1024:
            await processing_msg.edit_text(
                f"❌ File size: {output_size//1024}KB (max 256KB)\n"
                "💡 Try a shorter video (1-2 seconds) or simpler animation"
            )
            return

        # Send the converted file
        await processing_msg.edit_text("✅ Conversion complete! Uploading...")
        
        with open(output_path, 'rb') as video_file:
            caption = (
                f"🎉 Your {conversion_type} is ready!\n\n"
                f"• Format: WebM VP9 ✓\n"
                f"• Resolution: {resolution.replace(':', 'x')} ✓\n"
                f"• Size: {output_size//1024}KB ✓\n"
                f"• Audio: Removed ✓\n"
            )
            
            # Add transparency info for stickers
            if choice == "sticker":
                # Check if the output has transparency
                check_alpha_cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=pix_fmt',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    output_path
                ]
                
                try:
                    process_alpha = await asyncio.create_subprocess_exec(
                        *check_alpha_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process_alpha.communicate()
                    pix_fmt = stdout.decode().strip()
                    
                    if pix_fmt == 'yuva420p':
                        caption += "• Transparency: Supported ✓\n\n"
                    else:
                        caption += "• Transparency: Not detected (source may not have alpha channel)\n\n"
                except:
                    caption += "• Transparency: Unknown\n\n"
            else:
                caption += "\n"
                
            caption += "Ready to use in Telegram! ✅"
            
            await update.message.reply_document(
                document=video_file,
                filename=f"{conversion_type.lower().replace(' ', '_')}.webm",
                caption=caption
            )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    finally:
        # Cleanup temp files
        for path in [input_path, output_path, output_path + '_compressed.webm']:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset user's choice"""
    user_id = update.message.from_user.id
    if user_id in user_choices:
        del user_choices[user_id]
    
    keyboard = [
        [InlineKeyboardButton("🎥 Video Emoji", callback_data="emoji")],
        [InlineKeyboardButton("🖼️ Video Sticker", callback_data="sticker")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Choose what you want to create:",
        reply_markup=reply_markup
    )

def main():
    """Start the bot"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, convert_video))

        logger.info("Starting WebM Converter Bot...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")

if __name__ == '__main__':
    main()