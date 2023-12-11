import json
import os
import logging
import openai
import tiktoken
import urllib.parse

from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message, Update
from pymongo import MongoClient


def is_authed_user(_, client: Client, message: Message):
    return message.from_user.id in enabled_userids


def is_admin(_, client: Client, message: Message):
    return message.from_user.id in admin_userids


tg_api_id = os.getenv("TG_API_ID")
tg_api_hash = os.getenv("TG_API_HASH")
bot_token = os.getenv("TG_BOT_TOKEN_GPTCHATBOT")

openai.organization = os.getenv("OPENAI_ORGANIZATION")
openai.api_key = os.getenv("OPENAI_API_KEY")
chat_model = "gpt-3.5-turbo"
system_messages = [{"role": "system", "content": "You are a helpful assistant."}]

mongo_host = os.getenv("MONGO_HOST")
mongo_port = os.getenv("MONGO_PORT", 27017)
mongo_username = urllib.parse.quote_plus(os.getenv("MONGO_INITDB_ROOT_USERNAME"))
mongo_passwd = urllib.parse.quote_plus(os.getenv("MONGO_INITDB_ROOT_PASSWORD"))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Client("chatgpt-bot", tg_api_id, tg_api_hash, bot_token=bot_token)

mongo_client = MongoClient("mongodb://%s:%s@%s:%s" % (mongo_username, mongo_passwd, mongo_host, mongo_port))
db = mongo_client.get_database("chatgpt_bot")

enabled_users = db.get_collection("users").find({"enabled": True}, ["_id"])
enabled_userids = {user["_id"] for user in enabled_users}

admin_userids = {665409601}
admin_filter = filters.create(is_admin)
user_filter = filters.create(is_authed_user) | admin_filter


@app.on_message(group=-1)
async def audit_log(client: Client, message: Message):
    logging.info("Audit log: userid: %s", message.from_user.id)


@app.on_message(user_filter & filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply("I'm a chat bot powered by OpenAI ChatGPT! What can I help?")


@app.on_message(admin_filter & filters.command("addusers"))
async def addusers(client: Client, message: Message):
    userids = await get_userids_from_message(message)
    for userid in userids:
        db.get_collection("users").update_one(
            {"_id": userid},
            {"$set": {"enabled": True}},
            upsert=True
        )
    userids.extend(userids)
    await message.reply("Users added")


@app.on_message(admin_filter & filters.command("removeusers"))
async def removeusers(client: Client, message: Message):
    userids = await get_userids_from_message(message)
    db.get_collection("users").update_many(
        {"_id": {"$in": userids}},
        {"$set": {"enabled": False}}
    )
    for userid in userids:
        enabled_userids.remove(userid)
    await message.reply("Users removed")


# Don't move this up, or it will match commands before other listeners
@app.on_message(user_filter & filters.text)
async def chat(client: Client, message: Message):
    user = db.get_collection("users").find_one({"_id": message.from_user.id})
    chat_entity = {"role": "user", "content": message.text}
    chat_history: list = user["chat_history"] + chat_entity if "chat_history" in user else [chat_entity]
    response = openai.ChatCompletion.create(model=chat_model, messages=system_messages + chat_history)
    response_message = response['choices'][0]['message']
    await message.reply(response_message["content"])
    chat_history.append(response_message)
    while num_tokens_from_messages(chat_history) > 3000:
        chat_history.pop(0)


async def get_userids_from_message(message: Message):
    username_entities = [entity for entity in message.entities if entity.type == MessageEntityType.MENTION]
    user_names = [message.text[ent.offset:ent.offset + ent.length] for ent in username_entities]
    users = await app.get_users(user_names)
    return [user.id for user in users]


def num_tokens_from_messages(messages, model=chat_model):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo":  # note: future models may deviate from this
        num_tokens = 0
        for message in messages:
            num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
        num_tokens += 2  # every reply is primed with <im_start>assistant
        return num_tokens
    else:
        raise NotImplementedError(f"""num_tokens_from_messages() is not presently implemented for model {model}. See 
        https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to 
        tokens.""")


if __name__ == '__main__':
    app.run()
