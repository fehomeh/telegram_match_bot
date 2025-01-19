import logging
import os
from datetime import datetime, timedelta, timezone
from telegram import Update, ChatMember, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, ChatMemberHandler,
    CallbackQueryHandler
)
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import re
from phonenumbers import parse, is_valid_number, NumberParseException
from email_validator import validate_email, EmailNotValidError
# import json
# from bson.json_util import dumps


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
members_collection = db["members"]
member_group_collection = db["member_groups"]


# Helper function to check if a user is an admin
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]


# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user_id = update.effective_user.id
    logger.info("[start] args: %s", ', '.join(args))

    if args:
        context.user_data['group_id'] = str(args[0])

        keyboard = [
            [InlineKeyboardButton("Join Group 🎾", callback_data='start_join')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Hello! 👋\nI'm a racket sports bot 🎾.\n"
            + "I will guide you through the process of registration and participation.\n"
            + "First, we need to register you.\nClick the button below to register in the group:",
            reply_markup=reply_markup
        )

    elif admins_collection.find_one({"admin_id": user_id}):
        await update.message.reply_text("You're already registered as an admin!")
    else:
        await update.message.reply_text(
            "Welcome to the Padel Game Bot! \n"
            + "If you want to become a member of the group, use /join command\n"
            + "If you want to become a community admin, Please, add me to your group or channel first."
            + " Fetch the group via /getgroupid command.\n"
            + " Then, use /signup to register as a community admin.")


# Detect new group members and send a private invite
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_member in update.message.new_chat_members:
        if new_member.is_bot:
            continue  # Ignore bots

        group_id = update.effective_chat.id
        bot_username = (await context.bot.get_me()).username

        # Create a direct link to the /join command with the group ID
        join_link = f"https://t.me/{bot_username}?start=join_{group_id}"

        try:
            # Send a private message to the new member
            await context.bot.send_message(
                chat_id=new_member.id,
                text=f"👋 Welcome to *{update.effective_chat.title}*!\n\n"
                     f"To join the game, please register here: [Register Now]({join_link})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            # If the bot can't send a message (user hasn't started the bot)
            await update.message.reply_text(
                f"Welcome {new_member.full_name}! Please start the bot and register here: {join_link}",
                parse_mode='Markdown'
            )


# Command: /signup
async def signup(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(
        "Nice! Let's set match registration window in weeks.\n"
        "For example: 3 means that players will be able to register for games in upcoming three weeks."
    )
    return WEEK_RANGE


async def receive_week_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['week_range'] = update.message.text
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
    week_range = int(context.user_data['week_range'])
    court_limit = int(update.message.text)
    now = datetime.now(timezone.utc)
    now_date = now.date()

    now_with_week_range_added = now_date + timedelta(weeks=week_range)
    days_to_add = 6 - now_with_week_range_added.weekday() + 1
    open_till = now_date + timedelta(weeks=week_range) + timedelta(days=days_to_add)

    groups_collection.insert_one({
        "group_id": group_id,
        "name": group_name,
        "spreadsheet": spreadsheet,
        "court_limit": court_limit,
        "week_range": week_range,
        "admin_id": int(user_id),
        "deleted_at": None,
        "created_at": now,
        "registration_open_till": datetime(day=open_till.day, month=open_till.month, year=open_till.year)
    })
    admins_collection.update_one({"admin_id": user_id}, {"$push": {"groups": group_id}})
    await update.message.reply_text(
        f"Group '{group_name}' has been added successfully!"
        + f" Match registration is open till {open_till.strftime('%d.%m.%Y')} with the current match registration window.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Group addition canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# Command: /listgroups
async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    groups = groups_collection.find({"admin_id": user_id, "deleted_at": None})
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


# Command: /invite (Admin triggers this in the group)
async def invite_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    bot_username = (await context.bot.get_me()).username

    join_link = f"https://t.me/{bot_username}?start={group_id}"

    keyboard = [
        [InlineKeyboardButton("Join This Group 🎾", url=join_link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Click the button below to register for the game:\n",
        reply_markup=reply_markup
    )


# Handler to prevent non-admins from adding the bot to groups
async def check_admin_rights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, ChatMemberHandler):
        if update.chat_member.new_chat_member.status in ['member', 'administrator']:
            user_id = update.chat_member.new_chat_member.user.id
            if not admins_collection.find_one({"admin_id": user_id}):
                await context.bot.leave_chat(update.chat_member.chat.id)
                logger.info(f"Bot left chat {update.chat_member.chat.id} because the adder was not a registered admin.")


# ================== MEMBER FUNCTIONS ============================


# Conversation states for /join
NAME, SURNAME, PHONE, EMAIL = range(4)


# Start /join <group_id>
async def start_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        group_id = context.user_data.get('group_id') if context.user_data else context.args[0]
    except IndexError:
        group_id = None
    if group_id is None:
        await update.message.reply_text("Usage: /join <group_id>")
        return ConversationHandler.END
    logger.info("New member tries to join. User ID: %s Group ID: %s", user_id, group_id)

    message = None
    if update.message is not None:
        message = update.message
    elif update.callback_query.message is not None:
        await update.callback_query.answer()
        await update.callback_query.delete_message()
        message = update.callback_query.message

    if user_id == group_id or group_id is None:
        error_message = "Something went wrong. Please, try again from the beginning."
        await message.reply_text(error_message)
        return ConversationHandler.END

    member = members_collection.find_one({"user_id": user_id})
    if member is not None:
        admin = admins_collection.find_one({"groups": str(group_id)})
        if not admin:
            await message.reply_text(
                f"I cannot find the group you want to register in. Here is the group ID: *{group_id}*\n"
                + "Please, contact the group administrator.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END

        member_group_record = member_group_collection.find_one({"user_id": user_id, "group_id": group_id})
        if member_group_record is not None:
            await message.reply_text("You are already registered in this group.")
            return ConversationHandler.END
        member_group_collection.insert_one({
            "user_id": user_id,
            "group_id": group_id,
            "status": "active"
        })
        await message.reply_text("You are successfully registered!")
        return ConversationHandler.END

    context.user_data['group_id'] = group_id

    await message.reply_text(
        "Welcome! Let's get you registered.\nPlease enter your *Name* (at least 3 letters):",
        parse_mode='Markdown'
    )
    return NAME


# Validate Name
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not re.fullmatch(r'[A-Za-z]{3,}', name):
        await update.message.reply_text("Invalid name. Please enter at least 3 letters without special characters:")
        return NAME
    context.user_data['name'] = name
    await update.message.reply_text("Great! Now enter your *Surname*:", parse_mode='Markdown')
    return SURNAME


# Validate Surname
async def get_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    surname = update.message.text.strip()
    if not re.fullmatch(r'[A-Za-z]{3,}', surname):
        await update.message.reply_text("Invalid surname. Please enter at least 3 letters without special characters:")
        return SURNAME
    context.user_data['surname'] = surname
    await update.message.reply_text("Now, enter your *Phone Number* in the format +1234567890:", parse_mode='Markdown')
    return PHONE


# Validate Phone Number
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    try:
        phone_obj = parse(phone)
        if not is_valid_number(phone_obj):
            raise ValueError
    except (NumberParseException, ValueError):
        await update.message.reply_text("Invalid phone number. Please enter in the format +1234567890:")
        return PHONE
    context.user_data['phone'] = phone
    await update.message.reply_text("Lastly, enter your *Email* (or type 'skip'):", parse_mode='Markdown')
    return EMAIL


# Validate Optional Email
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if email.lower() != 'skip':
        try:
            validate_email(email)
        except EmailNotValidError:
            await update.message.reply_text("Invalid email. Please enter a valid email or type 'skip':")
            return EMAIL
        context.user_data['email'] = email
    else:
        context.user_data['email'] = None

    # Save to DB
    user = update.effective_user
    group_id = context.user_data['group_id']
    admin = admins_collection.find_one({"groups": str(group_id)})
    if not admin:
        await update.message.reply_text("I cannot find the group you want to register in.")
        return ConversationHandler.END

    group = groups_collection.find_one({"group_id": str(group_id), "admin_id": admin["admin_id"]})
    if not group:
        await update.message.reply_text("Admin deleted the group. Registration is not possible.")
        return ConversationHandler.END

    member_data = {
        "registration_name": context.user_data['name'],
        "registration_surname": context.user_data['surname'],
        "registration_phone_number": context.user_data['phone'],
        "registration_email": context.user_data['email'],
        "group_ids": [context.user_data['group_id']],
        "user_id": user.id,
        "messenger_first_name": user.first_name,
        "messenger_last_name": user.last_name,
        "messenger_username": user.username,
        "created_at": datetime.utcnow(),
    }
    members_collection.insert_one(member_data)
    member_group_collection.insert_one({
        "user_id": user.id,
        "group_id": context.user_data['group_id'],
    })

    await update.message.reply_text("🎉 You have been registered successfully!")

    # Notify Admin
    await context.bot.send_message(
        chat_id=admin["admin_id"],
        text=f"📢 New member registered:\n*Name:* {member_data['registration_name']} {member_data['registration_surname']}\n"
             + f"*Username*: {member_data['messenger_username']}\n"
             + f"*Phone:* {member_data['registration_phone_number']}\n*Group:*{group['name']}",
        parse_mode='Markdown'
    )

    return ConversationHandler.END


# Cancel Handler
async def cancel_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration canceled.")
    return ConversationHandler.END


# Participation Command
async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if update.effective_chat.type == "private":
        if len(args) < 2:
            await update.message.reply_text(
                "Please specify the group name or ID and match date (DD.MM.YYYY) to join."
                + " For example, 23.11.2023"
            )
            return
        group_query = {"$or": [{"group_id": args[0]}, {"name": args[0]}]}
        try:
            match_date = datetime.strptime(args[1], "%d.%m.%Y").date()
        except ValueError:
            await update.message.reply_text("Invalid date format. Use DD.MM.YYYY. For example, 23.11.2023")
            return
    else:
        group_query = {"group_id": update.effective_chat.id}
        try:
            match_date = datetime.strptime(args[0], "%d.%m.%Y").date()
        except (ValueError, IndexError):
            await update.message.reply_text("Please specify a valid match date (DD.MM.YYYY). For example, 23.11.2023")
            return

    group = groups_collection.find_one({**group_query, "deleted_at": None})
    member_group_collection.find_one({
        "user_id": user_id,
        "group_id": group['group_id'],
        "status": {"$ne": "active"}
    })
    if member_group_collection is not None:
        await update.message.reply_text("You cannot join matches in this group. Please, contact the administrator.")
        return
    if not group:
        await update.message.reply_text("This group has been deleted or does not exist.")
        return

    if match_date > group['registration_open_till'].date():
        await update.message.reply_text("Registration period has ended.")
        return

    if match_date.weekday() not in group['match_days']:
        await update.message.reply_text("Matches are not scheduled for the selected date.")
        return

    existing = db.matches.find_one({"user_id": user_id, "group_id": group['group_id'], "match_date": match_date})
    if existing:
        await update.message.reply_text("You're already registered for the selected match date.")
        return

    db.matches.insert_one({
        "user_id": user_id,
        "group_id": group['group_id'],
        "match_date": match_date,
        "registered_at": datetime.utcnow(),
    })

    registered_count = db.matches.count_documents({"group_id": group['group_id'], "match_date": match_date})
    max_slots = group['court_limit'] * 4

    if registered_count >= max_slots:
        await update.message.reply_text(
            f"You are added to the waiting list for the match on *{match_date}* with number {registered_count + 1}",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(f"You are successfully registered for the match on {match_date}!")


# Cancel Participation
async def cancel_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    group_id = update.effective_chat.id
    match = db.matches.find_one({"user_id": user_id, "group_id": group_id})
    if not match:
        await update.message.reply_text("You're not registered for any match.")
        return

    time_diff = match['match_date'] - datetime.utcnow().date()
    if time_diff.days >= 2:
        db.matches.delete_one({"_id": match['_id']})
        await update.message.reply_text("Your participation has been canceled.")
    else:
        await update.message.reply_text(
            "It's less than 48 hours. Please provide a replacement using /replace_player <username>.")


# Replace Player Command
async def replace_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /replace_player @username DD.MM.YYYY")
        return

    username = args[0]
    date_str = args[1]

    if not re.match(r'@\w+', username):
        await update.message.reply_text("Invalid username format. Use @username")
        return

    try:
        match_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text("Invalid date format. Use DD.MM.YYYY. For example, 21.11.2022")
        return

    user = members_collection.find_one({"messenger_username": username.strip('@')})
    if not user:
        await update.message.reply_text("User not found.")
        return

    if db.matches.find_one({"match_date": match_date, "user_id": user['user_id']}):
        await update.message.reply_text("The specified user is already registered for this match date.")
        return

    existing_match = db.matches.find_one({"match_date": match_date, "user_id": update.effective_user.id})
    if not existing_match:
        await update.message.reply_text("You are not registered for this match date.")
        return

    db.matches.update_one(
        {"_id": existing_match['_id']},
        {"$set": {"user_id": user["user_id"]}}
    )
    await update.message.reply_text(f"Replacement successful! {username} will now play on {date_str}.")
    await context.bot.send_message(user['user_id'],
                                   f"You have been added to the match on {date_str}!")


# ========== END OF MEMBER FUNCTIONS ===============

# ========== UTILS =====================


# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg=f"Exception while handling an update: {update}", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")


async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update and update.message:
        await update.message.reply_text(
            "Hello!\n I can help you with managing your group for match registrations or playing games.\n"
            + "Here are the available commands:\n"
            + "/start - to get a welcome message and walk you through the registration process.\n"
            + "/signup - to register as an admin.\n"
            + "/getgroupid - add this bot to your channel to get group ID for registration.\n"
            + "/addgroup - to add a new group or a channel to manage.\n"
            + "/listgroups - to see your registered groups in this bot.\n"
            + "/deletegroup - to delete one of the registered groups in this bot.\n"
            + "/updatesheet - to update the spreadsheet link for one of the groups.\n"
            + "/join - to join the group as a member.\n"
            + "/help - to see this message.\n"
        )
# Conversation states
GROUP_ID, GROUP_NAME, WEEK_RANGE, SPREADSHEET_LINK, COURT_LIMIT = range(5)


# Main function
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    add_group_handler = ConversationHandler(
        entry_points=[CommandHandler('addgroup', start_add_group)],
        states={
            GROUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_id)],
            GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_name)],
            WEEK_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_week_range)],
            SPREADSHEET_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_spreadsheet_link)],
            COURT_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_court_limit)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signup", signup))
    app.add_handler(CommandHandler("getgroupid", get_group_id))
    app.add_handler(add_group_handler)
    app.add_handler(CommandHandler("listgroups", list_groups))
    app.add_handler(CommandHandler("deletegroup", delete_group))
    app.add_handler(CommandHandler("updatesheet", update_sheet))
    app.add_handler(ChatMemberHandler(check_admin_rights, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(CommandHandler("invite", invite_members))

    # Member handlers:
    join_handler = ConversationHandler(
        entry_points=[CommandHandler('join', start_join), CallbackQueryHandler(start_join)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_surname)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        },
        fallbacks=[CommandHandler('cancel', cancel_join)]
    )

    app.add_handler(CommandHandler('join_match', join_match))
    app.add_handler(CommandHandler('cancel_match', cancel_match))
    app.add_handler(CommandHandler('replace_player', replace_player))
    app.add_handler(join_handler)

    # Utils handlers
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('help', help_message))

    app.run_polling()


if __name__ == '__main__':
    main()
