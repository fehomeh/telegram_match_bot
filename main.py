import logging
import os
from datetime import datetime
from telegram import Update, ChatMember, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, ChatMemberHandler
)
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["padel_bot"]
admins_collection = db["admins"]
groups_collection = db["groups"]


# Helper function to check if a user is an admin
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]


# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if admins_collection.find_one({"admin_id": user_id}):
        await update.message.reply_text("You're already registered as an admin!")
    else:
        await update.message.reply_text(
            "Welcome to the Padel Game Bot! Please, add me to your group or channel first.\n"
            + "Then, use /register to become verify your admin rights in that group.")


# Command: /register
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    admin_record = admins_collection.find_one({"admin_id": user_id})
    if not admin_record:
        admins_collection.insert_one({
            "_id": ObjectId(),
            "admin_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "groups": [],
            "created_at": datetime.utcnow()
        })
        await update.message.reply_text("%s, you're now registered as an admin! Use /addgroup to add your groups." % (user.username))
    else:
        await update.message.reply_text(
            "You're already registered as *%s %s.*" % (admin_record['first_name'], admin_record['last_name']),
            parse_mode='Markdown'
        )


# Command: /getgroupid
async def get_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"This group's ID is: {chat_id}")


# Conversation to add group step-by-step
async def start_add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Let's add your group! First, please send me your Telegram Group ID.\n"
        "Tip: You can get the group ID by adding this bot to the group and using the command /getgroupid."
    )
    return GROUP_ID


async def receive_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['group_id'] = update.message.text
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(context.user_data['group_id'], user_id)
    if chat_member.status not in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
        await update.message.reply_text("You must be an admin of this group to add it.")
        return ConversationHandler.END

    await update.message.reply_text("Great! Now, send me the Group Name.")
    return GROUP_NAME


async def receive_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['group_name'] = update.message.text
    await update.message.reply_text("Awesome! Now, please share the Google Spreadsheet link.")
    return SPREADSHEET_LINK


async def receive_spreadsheet_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['spreadsheet'] = update.message.text
    await update.message.reply_text("Finally, how many courts are available?")
    return COURT_LIMIT


async def receive_court_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    group_id = context.user_data['group_id']
    group_name = context.user_data['group_name']
    spreadsheet = context.user_data['spreadsheet']
    court_limit = update.message.text

    groups_collection.insert_one({
        "group_id": group_id,
        "name": group_name,
        "spreadsheet": spreadsheet,
        "court_limit": int(court_limit),
        "admin_id": user_id,
        "is_deleted": False
    })
    admins_collection.update_one({"admin_id": user_id}, {"$push": {"groups": group_id}})
    await update.message.reply_text(f"Group '{group_name}' has been added successfully!", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Group addition canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# Command: /listgroups
async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    groups = groups_collection.find({"admin_id": user_id, "is_deleted": False})
    response = "Your groups:\n"
    for group in groups:
        response += f"- {group['name']} (ID: {group['group_id']})\n"
    await update.message.reply_text(response if response != "Your groups:\n" else "You have no active groups.")


# Command: /deletegroup <group_id>
async def delete_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /deletegroup <group_id>")
        return

    group_id = context.args[0]
    result = groups_collection.update_one({"group_id": group_id, "admin_id": user_id}, {"$set": {"is_deleted": True}})
    if result.modified_count > 0:
        await update.message.reply_text(f"Group {group_id} has been soft deleted.")
    else:
        await update.message.reply_text("Group not found or you don't have permission to delete it.")


# Command: /updatesheet <group_id> <new_spreadsheet_link>
async def update_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /updatesheet <group_id> <new_spreadsheet_link>")
        return

    group_id, new_spreadsheet_link = context.args
    result = groups_collection.update_one(
        {"group_id": group_id, "admin_id": user_id},
        {"$set": {"spreadsheet": new_spreadsheet_link}}
    )
    if result.modified_count > 0:
        await update.message.reply_text(f"Spreadsheet link for group {group_id} has been updated.")
    else:
        await update.message.reply_text("Group not found or you don't have permission to update it.")


# Handler to prevent non-admins from adding the bot to groups
async def check_admin_rights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, ChatMemberHandler):
        if update.chat_member.new_chat_member.status in ['member', 'administrator']:
            user_id = update.chat_member.new_chat_member.user.id
            if not admins_collection.find_one({"admin_id": user_id}):
                await context.bot.leave_chat(update.chat_member.chat.id)
                logger.info(f"Bot left chat {update.chat_member.chat.id} because the adder was not a registered admin.")


# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg=f"Exception while handling an update: {update}", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")


async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update and update.message:
        await update.message.reply_text(
            "Hello!\n I can help you with managing your group for match registrations.\n"
            + "Here are the available commands:\n"
            + "/start - to get a welcome message and walk you through the registration process.\n"
            + "/getgroupid - add this bot to your channel to get group ID for registration.\n"
            + "/addgroup - to add a new group or a channel to manage.\n"
            + "/listgroups - to see your registered groups in this bot.\n"
            + "/deletegroup - to delete one of the registered groups in this bot.\n"
            + "/updatesheet - to update the spreadsheet link for one of the groups.\n"
            + "/help - to see this message.\n"
        )
# Conversation states
GROUP_ID, GROUP_NAME, SPREADSHEET_LINK, COURT_LIMIT = range(4)


# Main function
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('addgroup', start_add_group)],
        states={
            GROUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_id)],
            GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_name)],
            SPREADSHEET_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_spreadsheet_link)],
            COURT_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_court_limit)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("getgroupid", get_group_id))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("listgroups", list_groups))
    app.add_handler(CommandHandler("deletegroup", delete_group))
    app.add_handler(CommandHandler("updatesheet", update_sheet))
    app.add_handler(ChatMemberHandler(check_admin_rights, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('help', help_message))

    app.run_polling()


if __name__ == '__main__':
    main()
