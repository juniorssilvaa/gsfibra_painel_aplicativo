import json
from channels.generic.websocket import AsyncWebsocketConsumer

class UserStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # Enviar um status inicial online se o frontend esperar
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'online'
        }))

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        pass
