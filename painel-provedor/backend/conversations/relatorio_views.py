"""Relatórios de atendimento (encerramentos por atendente)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from dateutil.parser import isoparse

from django.db.models import Count
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from conversations.closure_audit import AUTOMATION_CLOSE_ACTIONS, MANUAL_CLOSE_ACTIONS
from conversations.models import Conversation, Inbox, Message
from core.models import AuditLog, Canal, Provedor, User
from core.support_account import fallback_provedor_for_niohub, is_hidden_from_provedor_user_lists

CLOSE_ACTIONS = AUTOMATION_CLOSE_ACTIONS + MANUAL_CLOSE_ACTIONS
AUTOMATION_KEY = 'automacao'
UNASSIGNED_KEY = 'nao_atribuido'


def _resolve_provedor(request):
    user = request.user
    provedor = None
    provedor_id_param = request.GET.get('provedor_id')
    if provedor_id_param and getattr(user, 'user_type', '') in ('superadmin', 'admin'):
        try:
            provedor = Provedor.objects.filter(id=int(provedor_id_param)).first()
        except (TypeError, ValueError):
            return None, Response({'error': 'provedor_id inválido'}, status=400)

    if not provedor:
        if getattr(user, 'provedor_id', None):
            provedor = Provedor.objects.filter(id=user.provedor_id).first()
        if not provedor and getattr(user, 'provedor', None):
            provedor = user.provedor
        if not provedor:
            provedor = Provedor.objects.filter(admins=user).first()
        if not provedor:
            provedor = fallback_provedor_for_niohub(user)

    if not provedor:
        return None, Response({'error': 'Provedor não encontrado'}, status=400)
    return provedor, None


def _parse_period(request):
    start_param = request.GET.get('start_date')
    end_param = request.GET.get('end_date')
    today = timezone.localdate()
    if start_param and end_param:
        try:
            start_d = datetime.strptime(start_param, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_param, '%Y-%m-%d').date()
        except ValueError:
            return None, Response(
                {'error': 'Use start_date e end_date no formato YYYY-MM-DD'},
                status=400,
            )
        if start_d > end_d:
            return None, Response({'error': 'Data inicial não pode ser maior que a final'}, status=400)
        if (end_d - start_d).days > 366:
            return None, Response({'error': 'Intervalo máximo: 366 dias'}, status=400)
    else:
        end_d = today
        start_d = end_d - timedelta(days=6)
    return (start_d, end_d), None


def _aware(dt):
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def _parse_iso(value):
    if not value:
        return None
    try:
        parsed = isoparse(str(value))
    except (TypeError, ValueError):
        return None
    return _aware(parsed)


def format_hms(total_seconds):
    total_seconds = int(max(0, round(total_seconds or 0)))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def format_percent(value):
    rounded = round(float(value or 0), 2)
    text = f'{rounded:.2f}'.rstrip('0').rstrip('.')
    return text or '0'


def format_media(value):
    return round(float(value or 0), 2)


def _display_name(user):
    full = f'{user.first_name or ""} {user.last_name or ""}'.strip()
    return (full or user.username or 'Atendente').upper()


def _agent_key(log, conversation):
    if log.action in AUTOMATION_CLOSE_ACTIONS:
        return AUTOMATION_KEY
    user = log.user
    if user and not is_hidden_from_provedor_user_lists(user):
        return f'user_{user.id}'
    if conversation and conversation.assignee_id:
        assignee = conversation.assignee
        if assignee and not is_hidden_from_provedor_user_lists(assignee):
            return f'user_{assignee.id}'
    return UNASSIGNED_KEY


class RelatorioAtendentesVisaoGeralView(APIView):
    """Atendimentos encerrados por atendente, por dia de encerramento."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if getattr(request.user, 'user_type', '') == 'agent':
            return Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)

        provedor, err = _resolve_provedor(request)
        if err:
            return err
        period, err = _parse_period(request)
        if err:
            return err
        start_d, end_d = period

        start_dt = _aware(datetime.combine(start_d, time.min))
        end_dt = _aware(datetime.combine(end_d + timedelta(days=1), time.min))
        day_count = (end_d - start_d).days + 1

        logs = list(
            AuditLog.objects.filter(
                provedor=provedor,
                action__in=CLOSE_ACTIONS,
                timestamp__gte=start_dt,
                timestamp__lt=end_dt,
            )
            .select_related('user')
            .order_by('timestamp')
        )

        conv_ids = []
        for log in logs:
            try:
                conv_ids.append(int(log.conversation_id))
            except (TypeError, ValueError):
                continue
        conversations = {
            c.id: c
            for c in Conversation.objects.filter(
                id__in=conv_ids,
                inbox__provedor=provedor,
            ).select_related('assignee')
        }

        user_ids = set()
        for log in logs:
            if log.user_id:
                user_ids.add(log.user_id)
        for conv in conversations.values():
            if conv.assignee_id:
                user_ids.add(conv.assignee_id)
        users_by_id = {u.id: u for u in User.objects.filter(id__in=user_ids)}

        counts = defaultdict(lambda: defaultdict(int))
        durations = defaultdict(list)
        labels = {
            AUTOMATION_KEY: 'AUTOMAÇÃO',
            UNASSIGNED_KEY: 'NÃO ATRIBUÍDO',
        }

        for log in logs:
            local_ts = timezone.localtime(log.timestamp)
            day_key = local_ts.date().isoformat()
            conv = None
            try:
                conv = conversations.get(int(log.conversation_id))
            except (TypeError, ValueError):
                conv = None
            key = _agent_key(log, conv)
            if key.startswith('user_'):
                uid = int(key.split('_', 1)[1])
                user = users_by_id.get(uid) or log.user
                if user:
                    labels[key] = _display_name(user)
            counts[key][day_key] += 1

            start = None
            if conv:
                attrs = conv.additional_attributes if isinstance(conv.additional_attributes, dict) else {}
                start = _parse_iso(attrs.get('assigned_at')) or conv.created_at
            if start:
                start = _aware(start)
                duration = (log.timestamp - start).total_seconds()
                if duration >= 0:
                    durations[key].append(duration)

        days = [start_d + timedelta(days=i) for i in range(day_count)]
        seen_keys = set(counts.keys()) | set(durations.keys())

        def sort_key(k):
            if k == AUTOMATION_KEY:
                return (0, '')
            if k == UNASSIGNED_KEY:
                return (2, '')
            return (1, labels.get(k, k))

        agent_keys = sorted(seen_keys, key=sort_key)
        grand_total = sum(sum(per_day.values()) for per_day in counts.values())
        all_durations = [s for items in durations.values() for s in items]

        agents = []
        series_by_day = []
        for day in days:
            iso = day.isoformat()
            row = {'date': iso, 'label': day.strftime('%d/%m')}
            for key in agent_keys:
                row[key] = counts[key].get(iso, 0)
            series_by_day.append(row)

        for key in agent_keys:
            total = sum(counts[key].values())
            dur_list = durations.get(key) or []
            avg_tma = (sum(dur_list) / len(dur_list)) if dur_list else 0
            agents.append({
                'id': key,
                'name': labels.get(key, key),
                'percent': format_percent((total / grand_total * 100) if grand_total else 0),
                'tma_seconds': int(round(avg_tma)),
                'tma': format_hms(avg_tma),
                'media': format_media(total / day_count if day_count else 0),
                'total': total,
            })

        overall_tma = (sum(all_durations) / len(all_durations)) if all_durations else 0
        return Response({
            'start_date': start_d.isoformat(),
            'end_date': end_d.isoformat(),
            'days': day_count,
            'agents': agents,
            'series': series_by_day,
            'totals': {
                'tma_seconds': int(round(overall_tma)),
                'tma': format_hms(overall_tma),
                'media': format_media(grand_total / day_count if day_count else 0),
                'total': grand_total,
            },
        })


CHANNEL_TYPE_LABEL = {
    'whatsapp': 'WhatsApp',
    'whatsapp_session': 'WhatsApp',
    'whatsapp_oficial': 'WhatsApp',
    'telegram': 'Telegram',
    'instagram': 'Instagram',
    'email': 'E-mail',
    'webchat': 'Chat Web',
    'app_mobile': 'Aplicativo',
}

RATING_META = (
    (1, 'Péssimo', '😡'),
    (2, 'Ruim', '😕'),
    (3, 'Regular', '😐'),
    (4, 'Bom', '🙂'),
    (5, 'Excelente', '🤩'),
    (0, 'Resposta inválida', ''),
)


def _inbox_canal_map(provedor):
    canais = {c.id: c for c in Canal.objects.filter(provedor=provedor)}
    mapping = {}
    for inbox in Inbox.objects.filter(provedor=provedor):
        canal = None
        if inbox.channel_id and str(inbox.channel_id).isdigit():
            canal = canais.get(int(inbox.channel_id))
        mapping[inbox.id] = {'inbox': inbox, 'canal': canal}
    return mapping


class RelatorioCanaisView(APIView):
    """Atendimentos e mensagens por canal no período."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if getattr(request.user, 'user_type', '') == 'agent':
            return Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
        provedor, err = _resolve_provedor(request)
        if err:
            return err
        period, err = _parse_period(request)
        if err:
            return err
        start_d, end_d = period
        start_dt = _aware(datetime.combine(start_d, time.min))
        end_dt = _aware(datetime.combine(end_d + timedelta(days=1), time.min))
        day_count = (end_d - start_d).days + 1
        modo = (request.GET.get('modo') or 'geral').strip().lower()

        inbox_map = _inbox_canal_map(provedor)
        selected = []
        for inbox_id, meta in inbox_map.items():
            canal = meta['canal']
            is_disparo = bool(canal and canal.somente_disparo)
            if modo == 'disparo' and not is_disparo:
                continue
            if modo != 'disparo' and is_disparo:
                continue
            selected.append(inbox_id)

        days = [start_d + timedelta(days=i) for i in range(day_count)]
        empty_totals = {'clientes': 0, 'recebidas': 0, 'enviadas': 0, 'templates': 0, 'total': 0}
        if not selected:
            return Response({
                'start_date': start_d.isoformat(),
                'end_date': end_d.isoformat(),
                'modo': modo,
                'channels': [],
                'series': [{'date': d.isoformat(), 'label': d.strftime('%d/%m')} for d in days],
                'totals': empty_totals,
            })

        logs = AuditLog.objects.filter(
            provedor=provedor,
            action__in=CLOSE_ACTIONS,
            timestamp__gte=start_dt,
            timestamp__lt=end_dt,
        ).values_list('conversation_id', 'timestamp')

        conv_ids = []
        log_times = []
        for cid, ts in logs:
            try:
                conv_ids.append(int(cid))
                log_times.append(ts)
            except (TypeError, ValueError):
                continue
        conversations = {
            c.id: c
            for c in Conversation.objects.filter(id__in=conv_ids, inbox__provedor=provedor).select_related('inbox', 'contact')
        }

        counts = defaultdict(lambda: defaultdict(int))
        contacts = defaultdict(set)
        for cid, ts in zip(conv_ids, log_times):
            conv = conversations.get(cid)
            if not conv:
                continue
            inbox_id = conv.inbox_id
            if selected and inbox_id not in selected:
                continue
            day_key = timezone.localtime(ts).date().isoformat()
            counts[inbox_id][day_key] += 1
            if conv.contact_id:
                contacts[inbox_id].add(conv.contact_id)

        inbox_ids = list(selected)
        msg_in = defaultdict(int)
        msg_out = defaultdict(int)
        templates = defaultdict(int)
        if inbox_ids:
            msg_rows = (
                Message.objects.filter(
                    conversation__inbox_id__in=inbox_ids,
                    created_at__gte=start_dt,
                    created_at__lt=end_dt,
                )
                .values('conversation__inbox_id', 'is_from_customer')
                .annotate(total=Count('id'))
            )
            for row in msg_rows:
                inbox_id = row['conversation__inbox_id']
                if row['is_from_customer']:
                    msg_in[inbox_id] += row['total']
                else:
                    msg_out[inbox_id] += row['total']
            for inbox_id, attrs in Message.objects.filter(
                conversation__inbox_id__in=inbox_ids,
                is_from_customer=False,
                created_at__gte=start_dt,
                created_at__lt=end_dt,
            ).values_list('conversation__inbox_id', 'additional_attributes'):
                if isinstance(attrs, dict) and (attrs.get('template') or attrs.get('template_name')):
                    templates[inbox_id] += 1

        keys = sorted(
            {k for k in inbox_ids if k in inbox_map},
            key=lambda iid: (
                (inbox_map[iid]['canal'].nome if inbox_map[iid]['canal'] else inbox_map[iid]['inbox'].name) or ''
            ).lower(),
        )
        grand_total = sum(sum(v.values()) for v in counts.values())
        channels = []
        series = []
        for day in days:
            iso = day.isoformat()
            row = {'date': iso, 'label': day.strftime('%d/%m')}
            for key in keys:
                row[str(key)] = counts[key].get(iso, 0)
            series.append(row)

        for inbox_id in keys:
            meta = inbox_map[inbox_id]
            canal = meta['canal']
            inbox = meta['inbox']
            tipo = (canal.tipo if canal else inbox.channel_type) or 'whatsapp'
            name = (canal.nome if canal else inbox.name) or CHANNEL_TYPE_LABEL.get(tipo, tipo)
            total = sum(counts[inbox_id].values())
            channels.append({
                'id': str(inbox_id),
                'name': name,
                'tipo': tipo,
                'tipo_label': CHANNEL_TYPE_LABEL.get(tipo, tipo.replace('_', ' ').title()),
                'clientes': len(contacts.get(inbox_id, ())),
                'empresa': 0,
                'recebidas': msg_in.get(inbox_id, 0),
                'enviadas': msg_out.get(inbox_id, 0),
                'templates': templates.get(inbox_id, 0),
                'percent': format_percent((total / grand_total * 100) if grand_total else 0),
                'total': total,
            })

        return Response({
            'start_date': start_d.isoformat(),
            'end_date': end_d.isoformat(),
            'modo': modo,
            'channels': channels,
            'series': series,
            'totals': {
                'clientes': sum(c['clientes'] for c in channels),
                'recebidas': sum(c['recebidas'] for c in channels),
                'enviadas': sum(c['enviadas'] for c in channels),
                'templates': sum(c['templates'] for c in channels),
                'total': grand_total,
            },
        })


class RelatorioSatisfacaoView(APIView):
    """Dashboard de pesquisa de satisfação no período."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if getattr(request.user, 'user_type', '') == 'agent':
            return Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
        provedor, err = _resolve_provedor(request)
        if err:
            return err
        period, err = _parse_period(request)
        if err:
            return err
        start_d, end_d = period
        start_dt = _aware(datetime.combine(start_d, time.min))
        end_dt = _aware(datetime.combine(end_d + timedelta(days=1), time.min))
        day_count = (end_d - start_d).days + 1
        days_param = max(day_count, (timezone.localdate() - start_d).days + 1)

        from conversations.csat_service import CSATService
        from conversations.models import CSATFeedback

        stats = CSATService.get_csat_stats(provedor, days=days_param)
        daily = []
        for item in stats.get('daily_stats') or []:
            day = str(item.get('day') or '')[:10]
            if day < start_d.isoformat() or day > end_d.isoformat():
                continue
            dt = datetime.strptime(day, '%Y-%m-%d')
            daily.append({
                'date': day,
                'label': dt.strftime('%d/%m'),
                'count': item.get('count') or 0,
                'avg_rating': item.get('avg_rating') or 0,
            })
        existing = {d['date'] for d in daily}
        for i in range(day_count):
            day = start_d + timedelta(days=i)
            iso = day.isoformat()
            if iso not in existing:
                daily.append({'date': iso, 'label': day.strftime('%d/%m'), 'count': 0, 'avg_rating': 0})
        daily.sort(key=lambda d: d['date'])

        rating_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for item in stats.get('rating_distribution') or []:
            try:
                rv = int(item.get('rating_value') or 0)
            except (TypeError, ValueError):
                rv = 0
            if rv not in rating_counts:
                rv = 0
            rating_counts[rv] += int(item.get('count') or 0)

        agent_ratings = defaultdict(lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 0: 0})
        local_period_count = 0
        try:
            from conversations.csat_service import CSATService as _svc
            local_fbs = list(
                CSATFeedback.objects.filter(
                    provedor=provedor,
                    feedback_sent_at__gte=start_dt,
                    feedback_sent_at__lt=end_dt,
                ).values('conversation_id', 'rating_value')
            )
            local_period_count = len(local_fbs)
            agent_by_conv = _svc._resolve_agents_for_conversations(
                provedor,
                [{'conversation_id': f['conversation_id']} for f in local_fbs],
            )
            users = {
                u.id: (f'{u.first_name or ""} {u.last_name or ""}'.strip() or u.username)
                for u in User.objects.filter(id__in=set(agent_by_conv.values()))
            }
            for fb in local_fbs:
                aid = agent_by_conv.get(fb['conversation_id'])
                name = users.get(aid, 'Sem usuário')
                try:
                    rv = int(fb.get('rating_value') or 0)
                except (TypeError, ValueError):
                    rv = 0
                if rv not in (1, 2, 3, 4, 5):
                    rv = 0
                agent_ratings[name][rv] += 1
        except Exception:
            local_period_count = 0
            for item in stats.get('agent_ranking') or []:
                name = item.get('name') or 'Atendente'
                agent_ratings[name][4] += int(item.get('total_feedbacks') or 0)

        by_agent = [
            {'name': name, 'ratings': dict(vals), 'total': sum(vals.values())}
            for name, vals in sorted(agent_ratings.items(), key=lambda kv: -sum(kv[1].values()))
        ]
        period_total = sum(int(d.get('count') or 0) for d in daily)
        if local_period_count:
            for k in list(rating_counts.keys()):
                rating_counts[k] = 0
            for name, vals in agent_ratings.items():
                for rv, n in vals.items():
                    rating_counts[int(rv)] = rating_counts.get(int(rv), 0) + int(n)
            period_total = local_period_count
            valid = sum(rating_counts.get(i, 0) for i in (1, 2, 3, 4, 5))
            average_rating = (
                round(sum(i * rating_counts.get(i, 0) for i in (1, 2, 3, 4, 5)) / valid, 2)
                if valid else 0
            )
            satisfaction_rate = (
                round((rating_counts.get(4, 0) + rating_counts.get(5, 0)) / valid * 100, 1)
                if valid else 0
            )
        else:
            average_rating = stats.get('average_rating') or 0
            satisfaction_rate = stats.get('satisfaction_rate') or 0
            period_total = period_total or (stats.get('total_feedbacks') or 0)

        rating_labels = [{'value': v, 'label': lab, 'emoji': emo, 'count': rating_counts.get(v, 0)} for v, lab, emo in RATING_META]

        return Response({
            'start_date': start_d.isoformat(),
            'end_date': end_d.isoformat(),
            'total_feedbacks': period_total,
            'average_rating': average_rating,
            'satisfaction_rate': satisfaction_rate,
            'question': (
                'Como você avalia o atendimento de @atendente_nome? '
                'Digite apenas o número para selecionar a opção: '
                '1 - Péssimo 😡 2 - Ruim 😕 3 - Regular 😐 4 - Bom 🙂 5 - Excelente 🤩'
            ),
            'daily': daily,
            'rating_labels': rating_labels,
            'by_agent': by_agent,
            'agent_ranking': stats.get('agent_ranking') or [],
            'recent_feedbacks': [
                fb for fb in (stats.get('recent_feedbacks') or [])
                if not str(fb.get('feedback_sent_at') or '')[:10]
                or (
                    start_d.isoformat()
                    <= str(fb.get('feedback_sent_at') or '')[:10]
                    <= end_d.isoformat()
                )
            ],
        })

