"""
飞书通道接入

@author Saboteur7
@Date 2023/11/19
"""

# -*- coding=utf-8 -*-
import uuid

import PIL.Image
import requests
import web
from channel.feishu.feishu_message import FeishuMessage
from bridge.context import Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from common.singleton import singleton
from config import conf
from common.expired_dict import ExpiredDict
from bridge.context import ContextType
from channel.chat_channel import ChatChannel, check_prefix
from common import utils
import json
import os
import time
import easyocr
import PIL

URL_VERIFICATION = "url_verification"


@singleton
class FeiShuChanel(ChatChannel):
    feishu_app_id = conf().get('feishu_app_id')
    feishu_app_secret = conf().get('feishu_app_secret')
    feishu_token = conf().get('feishu_token')

    def __init__(self):
        super().__init__()
        # 历史消息id暂存，用于幂等控制
        self.receivedMsgs = ExpiredDict(60 * 60 * 7.1)
        logger.info("[FeiShu] app_id={}, app_secret={} verification_token={}".format(
            self.feishu_app_id, self.feishu_app_secret, self.feishu_token))
        # 无需群校验和前缀
        conf()["group_name_white_list"] = ["ALL_GROUP"]
        conf()["single_chat_prefix"] = []

    def startup(self):
        urls = (
            '/', 'channel.feishu.feishu_channel.FeishuController'
        )
        app = web.application(urls, globals(), autoreload=False)
        port = conf().get("feishu_port", 9891)
        web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))

    def send(self, reply: Reply, context: Context):
        msg = context.get("msg")
        is_group = context["isgroup"]
        if msg:
            access_token = msg.access_token
        else:
            access_token = self.fetch_access_token()
        headers = {
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
        }
        msg_type = "text"
        logger.info(f"[FeiShu] start send reply message, type={context.type}, content={reply.content}")
        reply_content = reply.content
        content_key = "text"
        if reply.type == ReplyType.IMAGE_URL:
            # 图片上传
            reply_content = self._upload_image_url(reply.content, access_token)
            if not reply_content:
                logger.warning("[FeiShu] upload file failed")
                return
            msg_type = "image"
            content_key = "image_key"
        if is_group:
            # 群聊中直接回复
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{msg.msg_id}/reply"
            data = {
                "msg_type": msg_type,
                "content": json.dumps({content_key: reply_content})
            }
            res = requests.post(url=url, headers=headers, json=data, timeout=(5, 10))
        else:
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {"receive_id_type": context.get("receive_id_type") or "open_id"}
            data = {
                "receive_id": context.get("receiver"),
                "msg_type": msg_type,
                "content": json.dumps({content_key: reply_content})
            }
            res = requests.post(url=url, headers=headers, params=params, json=data, timeout=(5, 10))
        res = res.json()
        if res.get("code") == 0:
            logger.info(f"[FeiShu] send message success")
        else:
            logger.error(f"[FeiShu] send message failed, code={res.get('code')}, msg={res.get('msg')}")

    def fetch_access_token(self) -> str:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
        headers = {
            "Content-Type": "application/json"
        }
        req_body = {
            "app_id": self.feishu_app_id,
            "app_secret": self.feishu_app_secret
        }
        data = bytes(json.dumps(req_body), encoding='utf8')
        response = requests.post(url=url, data=data, headers=headers)
        if response.status_code == 200:
            res = response.json()
            if res.get("code") != 0:
                logger.error(f"[FeiShu] get tenant_access_token error, code={res.get('code')}, msg={res.get('msg')}")
                return ""
            else:
                return res.get("tenant_access_token")
        else:
            logger.error(f"[FeiShu] fetch token error, res={response}")

    def fetch_username(self, user_id):
        base_url = "https://open.feishu.cn/open-apis/contact/v3/users/{}?department_id_type=open_department_id&user_id_type=user_id"
        url = base_url.format(user_id)
        payload = ''

        access_token = self.fetch_access_token()
        headers = {
            'Authorization': 'Bearer {}'.format(access_token)
        }

        response = requests.request("GET", url, headers=headers, data=payload)

        return response.json()['data']['user']['name']

    def _upload_image_url(self, img_url, access_token):
        logger.debug(f"[WX] start download image, img_url={img_url}")
        response = requests.get(img_url)
        suffix = utils.get_path_suffix(img_url)
        temp_name = str(uuid.uuid4()) + "." + suffix
        if response.status_code == 200:
            # 将图片内容保存为临时文件
            with open(temp_name, "wb") as file:
                file.write(response.content)

        # upload
        upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
        data = {
            'image_type': 'message'
        }
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        with open(temp_name, "rb") as file:
            upload_response = requests.post(upload_url, files={"image": file}, data=data, headers=headers)
            logger.info(f"[FeiShu] upload file, res={upload_response.content}")
            os.remove(temp_name)
            return upload_response.json().get("data").get("image_key")


class FeishuController:
    # 类常量
    FAILED_MSG = '{"success": false}'
    SUCCESS_MSG = '{"success": true}'
    MESSAGE_RECEIVE_TYPE = "im.message.receive_v1"

    def GET(self):
        return "Feishu service start success!"

    def POST(self):
        try:
            channel = FeiShuChanel()

            request = json.loads(web.data().decode("utf-8"))
            logger.debug(f"[FeiShu] receive request: {request}")

            # 1.事件订阅回调验证
            if request.get("type") == URL_VERIFICATION:
                varify_res = {"challenge": request.get("challenge")}
                return json.dumps(varify_res)

            # 2.消息接收处理
            # token 校验
            header = request.get("header")
            if not header or header.get("token") != channel.feishu_token:
                return self.FAILED_MSG

            # 处理消息事件
            event = request.get("event")
            if header.get("event_type") == self.MESSAGE_RECEIVE_TYPE and event:
                if not event.get("message") or not event.get("sender"):
                    logger.warning(f"[FeiShu] invalid message, msg={request}")
                    return self.FAILED_MSG
                msg = event.get("message")

                # 幂等判断
                if channel.receivedMsgs.get(msg.get("message_id")):
                    logger.warning(f"[FeiShu] repeat msg filtered, event_id={header.get('event_id')}")
                    return self.SUCCESS_MSG
                channel.receivedMsgs[msg.get("message_id")] = True

                self._forward(request, channel, conf().get("keyword"))

                is_group = False
                chat_type = msg.get("chat_type")
                if chat_type == "group":
                    if not msg.get("mentions") and msg.get("message_type") == "text":
                        # 群聊中未@不响应
                        return self.SUCCESS_MSG
                    if msg.get("message_type") == "text" and msg.get("mentions")[0].get("name") != conf().get("feishu_bot_name"):
                        # 不是@机器人，不响应
                        return self.SUCCESS_MSG
                    # 群聊
                    is_group = True
                    receive_id_type = "chat_id"
                elif chat_type == "p2p":
                    receive_id_type = "open_id"
                else:
                    logger.warning("[FeiShu] message ignore")
                    return self.SUCCESS_MSG
                # 构造飞书消息对象
                feishu_msg = FeishuMessage(event, is_group=is_group, access_token=channel.fetch_access_token())
                if not feishu_msg:
                    return self.SUCCESS_MSG

                context = self._compose_context(
                    feishu_msg.ctype,
                    feishu_msg.content,
                    isgroup=is_group,
                    msg=feishu_msg,
                    receive_id_type=receive_id_type,
                    no_need_at=True
                )
                if context:
                    channel.produce(context)
                logger.info(f"[FeiShu] query={feishu_msg.content}, type={feishu_msg.ctype}")
            return self.SUCCESS_MSG

        except Exception as e:
            logger.error(e)
            return self.FAILED_MSG

    def _compose_context(self, ctype: ContextType, content, **kwargs):
        context = Context(ctype, content)
        context.kwargs = kwargs
        if "origin_ctype" not in context:
            context["origin_ctype"] = ctype

        cmsg = context["msg"]
        context["session_id"] = cmsg.from_user_id
        context["receiver"] = cmsg.other_user_id

        if ctype == ContextType.TEXT:
            # 1.文本请求
            # 图片生成处理
            img_match_prefix = check_prefix(content, conf().get("image_create_prefix"))
            if img_match_prefix:
                content = content.replace(img_match_prefix, "", 1)
                context.type = ContextType.IMAGE_CREATE
            else:
                context.type = ContextType.TEXT
            context.content = content.strip()

        elif context.type == ContextType.VOICE:
            # 2.语音请求
            if "desire_rtype" not in context and conf().get("voice_reply_voice"):
                context["desire_rtype"] = ReplyType.VOICE

        return context

    # written by summer sheng
    # get called in handler function
    # whenever a message sent to the group chat with the bot
    # this function forward it to a specific group
    def _forward(self, request, channel, keyword):
        # try to get the info

        try:
            message_id = request['event']['message']['message_id']
            user_id = request['event']['sender']['sender_id']['user_id']
            content = request['event']['message']['content']
            msg_type = request['event']['message']['message_type']
            print(request)
        except:
            message_id = None
            user_id = None
            content = None

        # if the info is not None, forward it to the specified group
        # check if the message is new, if it has been forwarded before
        # then ignore it
        if message_id is not None and self._is_new(request):
            access_token = channel.fetch_access_token()
            user_name = channel.fetch_username(user_id)
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"

            # resend text message
            if msg_type == 'text' and self._is_relevant(channel=channel, request=request, keyword='天气'):
                message = content.split(":")[1][1:-2]

            # todo make forwarding images work
            elif msg_type == "image":

                message = self._read_image(request, access_token)
                if not self._is_relevant(channel=channel,keyword=keyword,request=request, img_message=message):
                    return self.SUCCESS_MSG
            else:
                return self.SUCCESS_MSG

            forward_message = "{\"text\":" + "\"" + user_name + ": " + message + "\"" + "}"

            payload = json.dumps({
                "content": forward_message,
                "msg_type": "text",
                "receive_id": conf().get("feishu_group_chat_destination"),
            })

            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {}'.format(access_token)
            }

            response = requests.request("POST", url, headers=headers, data=payload)
            return response.text

    def _is_relevant(self, channel, keyword, request, img_message=None):
        feishu_msg = FeishuMessage(request['event'], is_group=True, access_token=channel.fetch_access_token())
        receive_id_type = "chat_id"
        content = request['event']['message']['content']
        msg_type = request['event']['message']['message_type']

        if msg_type == "image":
            message = img_message
        elif msg_type == "text":
            # strip \"\"
            message = content.split(":")[1][1:-2]
        else:
            message = None

        query = "你是{}的专家，请只用是或否回答， 这句句子\"{}\"， 是否和{}相关？".format(keyword, message, keyword)
        context = self._compose_context(
            ContextType.TEXT,
            query,
            isgroup=True,
            no_need_at=False,
            msg=feishu_msg,
            receive_id_type=receive_id_type,
        )
        reply = channel.build_reply_content(query=query, context=context).content

        return reply[0].lower() in ["yes.", '是。', '是', 'yes']

    def _is_new(self, request):
        message_time = int(request['event']['message']['create_time'])
        now = int(round(1000 * time.time()))
        return now - message_time <= 10000


    def _read_image(self, request, access_token):
        image_key = (request['event']['message']['content']).split(":")[1][1:-2]
        url = "https://open.feishu.cn/open-apis/im/v1/images/{}".format(image_key)
        payload = ''

        headers = {
            'Authorization': 'Bearer {}'.format(access_token)
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        import io
        temp_name = str(uuid.uuid4()) + "." + "jpeg"
        if response.status_code == 200:
            # 将图片内容保存为临时文件
            with open(temp_name, "wb") as file:
                file.write(response.content)
        img = PIL.Image.open(temp_name)

        # todo make it read from the command line
        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)  # this needs to run only once to load the model into memory

        result = reader.readtext(img, detail=0)
        content = ""
        for words in result:
            content += words
        return content
