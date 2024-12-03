import botpy
from botpy.message import Message

class AiChanQQ(botpy.Client):
    async def on_at_message_create(self, message: Message):
        await self.api.post_message(msg_id=message.id, channel_id=message.channel_id, content="你好啊！")
