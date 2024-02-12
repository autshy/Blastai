import sys

from bridge.context import *
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel, check_prefix
from channel.chat_message import ChatMessage
from config import conf
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from PIL import Image
import easyocr
import json


class TelegramMessage(ChatMessage):
    def __init__(
        self,
        msg_id,
        content,
        ctype=ContextType.TEXT,
        from_user_id="User",
        to_user_id="Chatgpt",
        other_user_id="Chatgpt",
    ):
        self.msg_id = msg_id
        self.ctype = ctype
        self.content = content
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id
        self.other_user_id = other_user_id


class TelegramChannel(ChatChannel):
    def __init__(self):
        self.bot_token = conf().get("telegram_token")
        self.application = Application.builder().token(self.bot_token).build()
        self.keyword = conf().get('keyword')

    async def downloader(update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_file = await update.message.effective_attachment[-1].get_file()
        file = await new_file.download_to_drive()
        return file

    async def download_relevant_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        content = ""
        if update.message.photo:
            img_file = await update.message.effective_attachment[-1].get_file()
            file = await img_file.download_to_drive()
            image = Image.open(file)
            caption = update.message.caption if update.message.caption is not None else ""
            reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
            result = reader.readtext(image, detail=0)

            for word in result:
                content += word
            content += caption
        elif update.message.text:
            content = update.message.text
        else:
            pass

        prompt = "想象你是{}的专家，请问 \"{}\" 和 {} 相关吗？请只用是或否回答。".format(self.keyword, content, self.keyword)
        context = self._compose_context(ContextType.TEXT, prompt, msg=TelegramMessage(update.message.message_id, prompt))
        if context:
            self.produce(context)
        else:
            raise Exception("context is None")
        reply = self.build_reply_content(query=prompt, context=context).content
        print(reply)

        if reply[0] == "是":
            data = content
            platform = "Telegram"
            image_url = None
            author_name = None

            data_to_store = {
                'url': image_url,
                'data': data,
                'platform': platform,
                'author': author_name
            }
            write_to_json(data_to_store)

    def startup(self):
        self.application.add_handler(MessageHandler(filters.ALL, self.download_relevant_info))
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def write_to_json(data):
    json_file_path = "dataset.json"

    # Open the file in append mode
    with open(json_file_path, 'a', encoding='utf-8') as json_file:
        # Move the cursor to the end of the file
        json_file.seek(0, 2)

        # If the file is not empty, add a comma before appending the new data
        if json_file.tell() > 0:
            json_file.write(',')

        # Convert the dictionary to a JSON-formatted string and append it to the file
        json.dump(data, json_file, ensure_ascii=False)
        # Add a newline character for better readability
        json_file.write('\n')

    print(f"Data has been appended to {json_file_path}")



