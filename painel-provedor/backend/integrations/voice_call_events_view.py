"""
SSE de eventos de ligação (proxy assíncrono → NioHub Calls).
Autenticação: ?ticket= (curto) ou Authorization: Token (header).
"""
import json
import logging

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import StreamingHttpResponse
from django.views import View

from integrations.niohub_voice_calls import voice_calls_configured

logger = logging.getLogger(__name__)


@sync_to_async
def _user_from_request(request):
    from core.auth_token_cache import user_from_token_key
    from core.realtime_tickets import allow_legacy_token_query, user_from_realtime_ticket

    ticket = (request.GET.get('ticket') or request.GET.get('rt') or '').strip()
    if ticket:
        return user_from_realtime_ticket(ticket)

    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if auth.startswith('Token '):
        return user_from_token_key(auth[7:].strip())

    legacy = (request.GET.get('token') or '').strip()
    if legacy and allow_legacy_token_query():
        return user_from_token_key(legacy)

    return None


class VoiceCallEventsView(View):
    async def get(self, request):
        user = await _user_from_request(request)
        if not user:
            return StreamingHttpResponse(
                'data: {"type":"error","message":"Não autenticado."}\n\n',
                content_type='text/event-stream',
                status=401,
            )

        if not voice_calls_configured():
            return StreamingHttpResponse(
                'data: {"type":"error","message":"Serviço de ligações não configurado."}\n\n',
                content_type='text/event-stream',
                status=503,
            )

        response = StreamingHttpResponse(
            self._iter_proxy_events(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    async def _iter_proxy_events(self):
        base = getattr(settings, 'NIOHUB_CALLS_BASE_URL', '').strip().rstrip('/')
        params = {}
        api_key = getattr(settings, 'NIOHUB_CALLS_API_KEY', '').strip()
        if api_key:
            params['apiKey'] = api_key
        url = f'{base}/api/events'

        try:
            timeout = httpx.Timeout(connect=20.0, read=None, write=30.0, pool=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream('GET', url, params=params) as resp:
                    if resp.status_code >= 400:
                        err = json.dumps(
                            {'type': 'error', 'message': f'SSE upstream HTTP {resp.status_code}'},
                            ensure_ascii=False,
                        )
                        yield f'data: {err}\n\n'
                        return

                    buffer = ''
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while True:
                            line_end = buffer.find('\n')
                            if line_end < 0:
                                break
                            line = buffer[:line_end].rstrip('\r')
                            buffer = buffer[line_end + 1:]
                            if not line.startswith('data:'):
                                continue
                            payload_text = line[5:].strip()
                            if payload_text in ('', '[DONE]'):
                                continue
                            yield f'data: {payload_text}\n\n'
                            yield ': flush\n\n'
        except Exception as exc:
            logger.warning('[NioHubCalls] SSE async proxy: %s', exc)
            err = json.dumps({'type': 'error', 'message': str(exc)[:200]}, ensure_ascii=False)
            yield f'data: {err}\n\n'
