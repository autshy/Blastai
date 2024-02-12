import discord
from discord.ext import commands
from config import conf
import re
import easyocr
from channel.discords.discord_message import DiscordMessage
from bridge.context import *
from channel.chat_channel import ChatChannel, check_prefix
import json

# Summer Sheng
# in this class, we only assume that the message would be sent by tweetshift robot
# not any human beings, so it will not respond if you send an image in the group chat
# since the format of an image sent by a bot is different from the format of the image sent by a user
class DiscordChannel(commands.Bot, ChatChannel):
    def __init__(self, command_prefix=""):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.bot_token = conf().get("discord_token")
        self.keyword = conf().get('keyword')

    async def on_ready(self):
        print(f'Logged in as {self.user.name} ({self.user.id})')
        print('------')

    async def on_message(self, message):
        text = message.content.split("[")[0]
        author_name = message.author.name[:message.author.name.find('• TweetShift' )]

        found, url = extract_image_url(message.content)
        if found:
            text += read_image_from_url(url)

        prompt = "想象你是{}的专家，请问 \"{}\" 和 {} 相关吗？请只用是或否回答。".format(self.keyword, text, self.keyword)
        context = self._compose_context(ContextType.TEXT, prompt, msg=DiscordMessage(message.id, prompt))
        if context:
            self.produce(context)
        else:
            raise Exception("context is None")
        reply = self.build_reply_content(query=prompt, context=context).content
        # todo basing on the business requirement
        # download certain messages depending on reply

        if reply[0] == "是":
            data = text
            platform = "Twitter"
            image_url = url

            data_to_store = {
                'url': image_url,
                'data': data,
                'platform': platform,
                'author': author_name
            }
            write_to_json(data_to_store)

    def startup(self):
        self.run(self.bot_token)


def extract_image_url(text):
    # extract url from the text
    pattern = r'(https?|ftp):\/\/[^\s\/$.?#].[^\s]*\.(jpg|jpeg|png|gif|bmp)'
    match = re.search(pattern, text)

    if match:
        found_url = match.group()
        return True, found_url
    else:
        return False, None


def read_image_from_url(url):
    # directly send the url to the ocr reader
    # if supports chinese and english
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
    result = reader.readtext(url, detail=0)
    content = ""

    for word in result:
        content += word
    return content


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
