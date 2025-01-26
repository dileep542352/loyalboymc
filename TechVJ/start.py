import os
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import UsernameNotOccupied
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from config import API_ID, API_HASH, ERROR_MESSAGE
from database.db import db
from TechVJ.strings import HELP_TXT

class BatchStatus:
    IS_BATCH = {}

async def update_status(client, statusfile, message, chat, prefix):
    while not os.path.exists(statusfile):
        await asyncio.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as file:
            progress = file.read()
        try:
            await client.edit_message_text(chat, message.id, f"**{prefix}:** **{progress}**")
            await asyncio.sleep(10)
        except:
            await asyncio.sleep(5)

def progress(current, total, message, type):
    with open(f'{message.id}{type}status.txt', "w") as file:
        file.write(f"{current * 100 / total:.1f}%")

@Client.on_message(filters.command(["start"]))
async def send_start(client: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
    buttons = [
        [InlineKeyboardButton("❣️ Developer", url="https://t.me/kingvj01")],
        [InlineKeyboardButton('🔍 Support Group', url='https://t.me/vj_bot_disscussion'),
         InlineKeyboardButton('🤖 Update Channel', url='https://t.me/vj_botz')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await client.send_message(
        chat_id=message.chat.id,
        text=f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot. "
             f"Use /login to access restricted content and /help to know more.</b>",
        reply_markup=reply_markup,
        reply_to_message_id=message.id
    )

@Client.on_message(filters.command(["help"]))
async def send_help(client: Client, message: Message):
    await client.send_message(chat_id=message.chat.id, text=f"{HELP_TXT}")

@Client.on_message(filters.command(["cancel"]))
async def send_cancel(client: Client, message: Message):
    BatchStatus.IS_BATCH[message.from_user.id] = True
    await client.send_message(chat_id=message.chat.id, text="**Batch Successfully Cancelled.**")

@Client.on_message(filters.text & filters.private)
async def save(client: Client, message: Message):
    if "https://t.me/" not in message.text:
        return

    if BatchStatus.IS_BATCH.get(message.from_user.id) == False:
        return await message.reply_text("**One task is already in progress. Use /cancel to stop it.**")

    datas = message.text.split("/")
    from_id, to_id = map(int, datas[-1].replace("?single", "").split("-"))
    BatchStatus.IS_BATCH[message.from_user.id] = False

    user_data = await db.get_session(message.from_user.id)
    if user_data is None:
        await message.reply("**Please /login first.**")
        BatchStatus.IS_BATCH[message.from_user.id] = True
        return

    async with Client("saverestricted", session_string=user_data, api_hash=API_HASH, api_id=API_ID) as acc:
        for msg_id in range(from_id, to_id + 1):
            if BatchStatus.IS_BATCH.get(message.from_user.id):
                break

            await process_message(client, acc, message, datas, msg_id)

    BatchStatus.IS_BATCH[message.from_user.id] = True

async def process_message(client, acc, message, datas, msg_id):
    try:
        if "https://t.me/c/" in message.text:
            chat_id = int("-100" + datas[4])
            await handle_private(client, acc, message, chat_id, msg_id)
        elif "https://t.me/b/" in message.text:
            username = datas[4]
            await handle_private(client, acc, message, username, msg_id)
        else:
            username = datas[3]
            msg = await client.get_messages(username, msg_id)
            if msg:
                await client.copy_message(message.chat.id, msg.chat.id, msg.id, reply_to_message_id=message.id)
            else:
                await client.send_message(message.chat.id, "The message is not available.", reply_to_message_id=message.id)
    except UsernameNotOccupied:
        await client.send_message(message.chat.id, "The username is not occupied by anyone", reply_to_message_id=message.id)
    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(message.chat.id, f"Error: {e}", reply_to_message_id=message.id)

async def handle_private(client: Client, acc, message: Message, chat_id, msg_id: int):
    msg = await acc.get_messages(chat_id, msg_id)
    if msg is None or msg.empty:
        await client.send_message(message.chat.id, "The message does not exist or is empty.", reply_to_message_id=message.id)
        return

    msg_type = get_message_type(msg)
    if not msg_type:
        return

    chat = message.chat.id
    smsg = await client.send_message(chat, '**Downloading**', reply_to_message_id=message.id)
    asyncio.create_task(update_status(client, f'{message.id}downstatus.txt', smsg, chat, "Downloaded"))

    try:
        file = await acc.download_media(msg, progress=progress, progress_args=[message, "down"])
        os.remove(f'{message.id}downstatus.txt')
    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(chat, f"Error: {e}", reply_to_message_id=message.id)
        await smsg.delete()
        return

    asyncio.create_task(update_status(client, f'{message.id}upstatus.txt', smsg, chat, "Uploaded"))
    caption = msg.caption or None

    try:
        await send_media(client, acc, msg, chat, file, caption, message.id)
    except Exception as e:
        if ERROR_MESSAGE:
            await client.send_message(chat, f"Error: {e}", reply_to_message_id=message.id)

    if os.path.exists(f'{message.id}upstatus.txt'):
        os.remove(f'{message.id}upstatus.txt')
        os.remove(file)
    await client.delete_messages(chat, [smsg.id])

async def send_media(client, acc, msg, chat, file, caption, reply_to_message_id):
    msg_type = get_message_type(msg)
    thumb = await download_thumb(acc, msg)

    if msg_type == "Document":
        await client.send_document(chat, file, thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Video":
        await client.send_video(chat, file, duration=msg.video.duration, width=msg.video.width, height=msg.video.height,
                                thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Animation":
        await client.send_animation(chat, file, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Sticker":
        await client.send_sticker(chat, file, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Voice":
        await client.send_voice(chat, file, caption=caption, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Audio":
        await client.send_audio(chat, file, thumb=thumb, caption=caption, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Photo":
        await client.send_photo(chat, file, caption=caption, reply_to_message_id=reply_to_message_id)
    elif msg_type == "Text":
        await client.send_message(chat, msg.text, entities=msg.entities, reply_to_message_id=reply_to_message_id)

async def download_thumb(acc, msg):
    try:
        if msg.document and msg.document.thumbs:
            return await acc.download_media(msg.document.thumbs[0].file_id)
        elif msg.video and msg.video.thumbs:
            return await acc.download_media(msg.video.thumbs[0].file_id)
    except:
        return None

def get_message_type(msg: Message):
    if msg.document:
        return "Document"
    if msg.video:
        return "Video"
    if msg.animation:
        return "Animation"
    if msg.sticker:
        return "Sticker"
    if msg.voice:
        return "Voice"
    if msg.audio:
        return "Audio"
    if msg.photo:
        return "Photo"
    if msg.text:
        return "Text"
    return None
