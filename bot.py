import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ===================== تنظیمات =====================
BOT_TOKEN  = "8849196850:AAHKeW3j4CdSFc-wVP5wVGU-DzAzdHECH5k"
ADMIN_ID   = 8584737764
CHANNEL_ID = -1003551470195

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── مراحل مکالمه کاربر ──
WAITING_TEXT, WAITING_PHOTO = range(2)

# ── مرحله ویرایش ادمین ──
WAITING_EDIT = 10

# اعلامیه‌های در انتظار تأیید  {admin_msg_id: {...}}
pending: dict[int, dict] = {}


# ═══════════════════════════════════════════════
#  بخش کاربر (پلیر)
# ═══════════════════════════════════════════════

async def entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """هر پیام متنی کاربر (غیر ادمین) وارد مکالمه می‌شه."""
    await update.message.reply_text(
        "⚔️ متن اعلامیه‌ات رو نوشتی.\n"
        "📸 حالا عکس رو بفرست:\n"
        "(اگه عکس نداری /skip بزن)"
    )
    context.user_data["ann_text"] = update.message.text
    return WAITING_PHOTO


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "⚔️ به ربات جنگی خوش آمدید!\n\n"
        "متن اعلامیه‌ات رو بنویس:"
    )
    return WAITING_TEXT


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ann_text"] = update.message.text
    await update.message.reply_text(
        "📸 حالا عکس رو بفرست:\n"
        "(اگه عکس نداری /skip بزن)"
    )
    return WAITING_PHOTO


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ann_photo"] = None
    await _send_to_admin(update, context)
    return ConversationHandler.END


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ann_photo"] = update.message.photo[-1].file_id
    await _send_to_admin(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ لغو شد.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  ارسال اعلامیه به ادمین
# ═══════════════════════════════════════════════

def _admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول",    callback_data="approve"),
        InlineKeyboardButton("✏️ ویرایش", callback_data="edit"),
        InlineKeyboardButton("❌ رد",      callback_data="reject"),
    ]])


async def _send_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    text     = context.user_data.get("ann_text", "")
    photo_id = context.user_data.get("ann_photo")

    admin_caption = (
        f"📨 اعلامیه جدید\n\n"
        f"👤 {user.full_name}  |  🆔 {user.id}\n\n"
        f"📝 متن:\n{text}"
    )

    if photo_id:
        msg = await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=admin_caption,
            reply_markup=_admin_keyboard(),
        )
    else:
        msg = await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_caption,
            reply_markup=_admin_keyboard(),
        )

    pending[msg.message_id] = {
        "user_id": user.id,
        "text":    text,
        "photo":   photo_id,
    }

    await update.message.reply_text(
        "✅ اعلامیه‌ات برای بررسی به ادمین فرستاده شد.\n"
        "برای ارسال اعلامیه جدید، دوباره متنت رو بنویس. ⚔️"
    )


# ═══════════════════════════════════════════════
#  پردازش دکمه‌های ادمین  (handler مستقل، خارج از ConversationHandler)
# ═══════════════════════════════════════════════

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # اگه غیر ادمین دکمه زد
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ فقط ادمین!", show_alert=True)
        return

    await query.answer()

    msg_id = query.message.message_id

    if msg_id not in pending:
        await _remove_keyboard(query, suffix="\n\n⚠️ این اعلامیه دیگه موجود نیست.")
        return

    ann  = pending[msg_id]
    data = query.data

    # ── قبول ──
    if data == "approve":
        await _publish(context, ann)
        await _remove_keyboard(query, suffix="\n\n✅ تأیید و منتشر شد.")
        await context.bot.send_message(
            chat_id=ann["user_id"],
            text="🎉 اعلامیه‌ات تأیید شد و در کانال منتشر شد! ⚔️",
        )
        del pending[msg_id]

    # ── رد ──
    elif data == "reject":
        await _remove_keyboard(query, suffix="\n\n❌ رد شد.")
        await context.bot.send_message(
            chat_id=ann["user_id"],
            text="😔 متأسفانه اعلامیه‌ات رد شد.",
        )
        del pending[msg_id]

    # ── ویرایش ──
    elif data == "edit":
        context.user_data["editing_msg_id"] = msg_id
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "✏️ متن (caption) جدید رو بنویس:\n\n"
                f"متن فعلی:\n{ann['text']}\n\n"
                "برای لغو /cancel_edit بزن."
            ),
        )


async def admin_cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data.pop("editing_msg_id", None)
    await update.message.reply_text("❌ ویرایش لغو شد.")


async def admin_receive_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام‌های متنی ادمین — فقط وقتی editing_msg_id ست باشه عمل می‌کنه."""
    if update.effective_user.id != ADMIN_ID:
        return

    msg_id = context.user_data.get("editing_msg_id")
    if not msg_id:
        return  # ادمین داره چیز دیگه‌ای می‌نویسه، کاری نداریم

    if msg_id not in pending:
        await update.message.reply_text("⚠️ اعلامیه دیگه موجود نیست.")
        context.user_data.pop("editing_msg_id", None)
        return

    new_text = update.message.text
    pending[msg_id]["text"] = new_text
    ann = pending[msg_id]

    new_caption = (
        f"📨 اعلامیه ویرایش‌شده\n\n"
        f"👤 🆔 {ann['user_id']}\n\n"
        f"📝 متن:\n{new_text}"
    )

    try:
        if ann["photo"]:
            await context.bot.edit_message_caption(
                chat_id=ADMIN_ID,
                message_id=msg_id,
                caption=new_caption,
                reply_markup=_admin_keyboard(),
            )
        else:
            await context.bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=msg_id,
                text=new_caption,
                reply_markup=_admin_keyboard(),
            )
    except Exception as e:
        logger.warning("edit_message error: %s", e)

    context.user_data.pop("editing_msg_id", None)
    await update.message.reply_text("✅ ویرایش ذخیره شد. حالا می‌تونی تأیید یا رد کنی.")


# ═══════════════════════════════════════════════
#  انتشار در کانال
# ═══════════════════════════════════════════════

async def _publish(context: ContextTypes.DEFAULT_TYPE, ann: dict):
    if ann["photo"]:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=ann["photo"],
            caption=ann["text"],
        )
    else:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=ann["text"],
        )


# ═══════════════════════════════════════════════
#  کمکی: حذف کیبورد
# ═══════════════════════════════════════════════

async def _remove_keyboard(query, suffix: str = ""):
    try:
        if query.message.caption is not None:
            old = query.message.caption or ""
            await query.edit_message_caption(caption=old + suffix)
        else:
            old = query.message.text or ""
            await query.edit_message_text(text=old + suffix)
    except Exception as e:
        logger.warning("remove_keyboard: %s", e)


# ═══════════════════════════════════════════════
#  اجرای ربات
# ═══════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # فیلتر: فقط کاربران غیر ادمین
    not_admin = ~filters.User(ADMIN_ID)

    # ConversationHandler کاربر
    user_conv = ConversationHandler(
        entry_points=[
            # استارت
            CommandHandler("start", start, filters=not_admin),
            # هر پیام متنی کاربر (بدون نیاز به /start)
            MessageHandler(filters.TEXT & ~filters.COMMAND & not_admin, entry_point),
        ],
        states={
            WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & not_admin, receive_text),
            ],
            WAITING_PHOTO: [
                MessageHandler(filters.PHOTO & not_admin, receive_photo),
                CommandHandler("skip", skip_photo, filters=not_admin),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel, filters=not_admin)],
        per_user=True,
        per_chat=False,
    )

    app.add_handler(user_conv)

    # دکمه‌های ادمین (مستقل از ConversationHandler)
    app.add_handler(CallbackQueryHandler(admin_callback))

    # پیام‌های متنی ادمین برای ویرایش
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),
            admin_receive_edit,
        )
    )

    # لغو ویرایش ادمین
    app.add_handler(
        CommandHandler("cancel_edit", admin_cancel_edit, filters=filters.User(ADMIN_ID))
    )

    logger.info("ربات روشن شد ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
