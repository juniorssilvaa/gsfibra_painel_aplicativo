"""Endpoints das Campanhas de disparo (admin/superadmin do provedor)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from django.db import transaction
from django.http import FileResponse
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from campaigns import service
from campaigns.csv_import import parse_recipients_csv
from campaigns.models import Campaign, CampaignRecipient
from conversations.ai_learning_views import _can_manage, _resolve_provedor_id
from core.models import Canal
from core.phone_utils import is_valid_whatsapp_phone, normalize_whatsapp_phone

EDITAVEIS = ('rascunho', 'agendada')
MAX_CSV_BYTES = 5 * 1024 * 1024
STATUS_DESTINATARIO = ('pendente', 'enviado', 'falhou', 'ignorado')
PUBLICOS = ('todos', 'contato', 'csv')
FORA_DO_PUBLICO = 'Fora do público escolhido no disparo'
NAO_SELECIONADO = 'Desmarcado na lista importada'
ORIGENS = ('contato', 'csv')


def _context(request):
    if not _can_manage(request.user):
        return None, Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return None, Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    return provedor_id, None


def _bad(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'error': msg}, status=code)


def _counts(campaign_ids):
    fora = Q(status='ignorado', erro=FORA_DO_PUBLICO)
    elegivel = Q(status='pendente') | fora
    rows = (
        CampaignRecipient.objects.filter(campanha_id__in=campaign_ids)
        .values('campanha_id')
        .annotate(
            total=Count('id'),
            **{s: Count('id', filter=Q(status=s)) for s in STATUS_DESTINATARIO},
            **{f'total_{o}': Count('id', filter=Q(origem=o)) for o in ORIGENS},
            **{f'elegivel_{o}': Count('id', filter=elegivel & Q(origem=o)) for o in ORIGENS},
            **{f'fora_{o}': Count('id', filter=fora & Q(origem=o)) for o in ORIGENS},
        )
    )
    empty = {
        'total': 0, **{s: 0 for s in STATUS_DESTINATARIO},
        **{f'{k}_{o}': 0 for k in ('total', 'elegivel', 'fora') for o in ORIGENS},
    }
    data = {cid: dict(empty) for cid in campaign_ids}
    for row in rows:
        data[row.pop('campanha_id')] = row
    return data


def _publico(counts) -> str:
    if counts.get('fora_contato'):
        return 'csv'
    if counts.get('fora_csv'):
        return 'contato'
    return 'todos'


def _canal_dict(canal):
    if canal is None:
        return None
    return {
        'id': canal.id,
        'nome': canal.nome or canal.phone_number or f'Canal {canal.id}',
        'tipo': canal.tipo,
        'tipo_label': service.CANAL_TIPOS.get(canal.tipo, canal.tipo),
        'texto_livre': canal.tipo in service.TEXTO_LIVRE_TIPOS,
    }


def _campaign_dict(c: Campaign, counts=None):
    counts = counts or _counts([c.id])[c.id]
    return {
        'id': c.id,
        'nome': c.nome,
        'status': c.status,
        'canal': _canal_dict(c.canal),
        'mensagem': c.mensagem,
        'template_name': c.template_name,
        'template_language': c.template_language,
        'template_variaveis': c.template_variaveis or [],
        'template_header_texto': c.template_header_texto,
        'template_header_url': c.template_header_url,
        'template_header_arquivo': os.path.basename(c.template_header_arquivo.name) if c.template_header_arquivo else None,
        'template_requisitos': service.template_requirements(c.template_def) if c.template_def else None,
        'agendada_para': c.agendada_para.isoformat() if c.agendada_para else None,
        'intervalo_segundos': c.intervalo_segundos,
        'erro': c.erro,
        'iniciada_em': c.iniciada_em.isoformat() if c.iniciada_em else None,
        'concluida_em': c.concluida_em.isoformat() if c.concluida_em else None,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'contagem': counts,
        'publico': _publico(counts),
    }


def _get_campaign(provedor_id, pk):
    return Campaign.objects.select_related('canal').filter(pk=pk, provedor_id=provedor_id).first()


def _clear_header_file(c: Campaign):
    if c.template_header_arquivo:
        c.template_header_arquivo.delete(save=False)
    c.template_header_arquivo = ''
    c.template_header_media_id = ''
    c.template_header_media_em = None


def _apply_payload(c: Campaign, data, provedor_id, strict=False):
    """Valida e aplica os campos editáveis. Retorna mensagem de erro ou None.

    strict=True (no disparo) também exige o que só faz falta na hora de enviar.
    """
    if 'nome' in data:
        c.nome = str(data.get('nome') or '').strip()[:150]
    if not c.nome:
        return 'Dê um nome para a campanha.'

    if 'canal_id' in data:
        canal = Canal.objects.filter(pk=data.get('canal_id') or 0, provedor_id=provedor_id).first()
        if canal is None or canal.tipo not in service.CANAL_TIPOS:
            return 'Escolha um canal válido (WhatsApp Oficial, WhatsApp QR code ou Telegram).'
        if c.canal_id and c.canal_id != canal.id and c.pk and c.destinatarios.exists():
            prev_tg = c.canal.tipo == 'telegram'
            if prev_tg != (canal.tipo == 'telegram'):
                return 'Remova os destinatários antes de trocar entre Telegram e WhatsApp.'
        c.canal = canal
    if c.canal is None:
        return 'Escolha o canal do disparo.'

    if 'intervalo_segundos' in data:
        try:
            c.intervalo_segundos = min(max(int(data.get('intervalo_segundos') or 0), 0), service.INTERVALO_MAX)
        except (TypeError, ValueError):
            return 'Intervalo entre envios inválido.'

    if c.canal.tipo == 'whatsapp_oficial':
        return _apply_template(c, data, strict)
    _clear_header_file(c)
    if 'mensagem' in data:
        c.mensagem = str(data.get('mensagem') or '').strip()[:4096]
    c.template_name = c.template_language = ''
    c.template_def = {}
    if not c.mensagem:
        return 'Escreva a mensagem do disparo.'
    return None


def _apply_template(c: Campaign, data, strict=False):
    from core.inbound_webhook_send import _find_meta_template

    name = str(data.get('template_name', c.template_name) or '').strip()
    language = str(data.get('template_language', c.template_language) or 'pt_BR').strip()
    if not name:
        return 'No WhatsApp Oficial a campanha usa um template aprovado pela Meta. Escolha o template.'
    if name != c.template_name or language != c.template_language or not c.template_def:
        template = _find_meta_template(c.canal, name, language)
        if not template:
            return f'Template "{name}" não encontrado neste canal.'
        if str(template.get('status') or '').upper() != 'APPROVED':
            return f'O template "{name}" ainda não está aprovado pela Meta.'
        if c.template_name and name != c.template_name:
            _clear_header_file(c)
        c.template_def = {'components': template.get('components') or [], 'category': template.get('category')}
        c.template_name, c.template_language = name, template.get('language') or language
    if 'template_variaveis' in data:
        c.template_variaveis = [str(v or '')[:1000] for v in (data.get('template_variaveis') or [])][:20]
    if 'template_header_texto' in data:
        c.template_header_texto = str(data.get('template_header_texto') or '')[:255]
    if 'template_header_url' in data:
        c.template_header_url = str(data.get('template_header_url') or '').strip()[:1000]
        if c.template_header_url:
            _clear_header_file(c)
    c.mensagem = ''

    req = service.template_requirements(c.template_def)
    if not req['suportado']:
        return req['motivo']
    if strict and req['header_media'] and not (c.template_header_url or c.template_header_arquivo):
        return 'Este template tem imagem/vídeo/documento no cabeçalho: envie o arquivo ou informe o link.'
    return None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def campaigns(request):
    provedor_id, err = _context(request)
    if err:
        return err
    if request.method == 'GET':
        items = list(Campaign.objects.select_related('canal').filter(provedor_id=provedor_id)[:200])
        counts = _counts([c.id for c in items])
        return Response({'results': [_campaign_dict(c, counts[c.id]) for c in items]})

    c = Campaign(provedor_id=provedor_id, criada_por=request.user)
    error = _apply_payload(c, request.data, provedor_id)
    if error:
        return _bad(error)
    c.save()
    return Response(_campaign_dict(c), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def campaign_detail(request, pk):
    provedor_id, err = _context(request)
    if err:
        return err
    c = _get_campaign(provedor_id, pk)
    if c is None:
        return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(_campaign_dict(c))
    if request.method == 'DELETE':
        if c.status == 'enviando':
            return _bad('Cancele a campanha antes de excluir.')
        if c.template_header_arquivo:
            c.template_header_arquivo.delete(save=False)
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if c.status not in EDITAVEIS:
        return _bad('Só é possível editar campanhas em rascunho ou agendadas.')
    error = _apply_payload(c, request.data, provedor_id)
    if error:
        return _bad(error)
    c.save()
    return Response(_campaign_dict(c))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def channels(request):
    provedor_id, err = _context(request)
    if err:
        return err
    items = Canal.objects.filter(provedor_id=provedor_id, tipo__in=list(service.CANAL_TIPOS)).order_by('id')
    return Response({'results': [{**_canal_dict(c), 'problema': service.channel_issue(c)} for c in items]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def templates(request):
    from integrations.whatsapp_templates import list_message_templates

    provedor_id, err = _context(request)
    if err:
        return err
    canal = Canal.objects.filter(
        pk=request.query_params.get('canal_id') or 0, provedor_id=provedor_id, tipo='whatsapp_oficial'
    ).first()
    if canal is None:
        return _bad('Canal WhatsApp Oficial não encontrado')
    ok, items, error = list_message_templates(canal, limit=100)
    if not ok:
        return _bad(error or 'Não foi possível listar os templates na Meta', status.HTTP_502_BAD_GATEWAY)
    results = []
    for t in items or []:
        if str(t.get('status') or '').upper() != 'APPROVED':
            continue
        req = service.template_requirements({'components': t.get('components') or []})
        results.append({
            'id': t.get('id'),
            'name': t.get('name'),
            'language': t.get('language'),
            'category': t.get('category'),
            'status': t.get('status'),
            'components': t.get('components') or [],
            'last_updated_time': t.get('last_updated_time'),
            'requisitos': req,
        })
    return Response({'results': results})


def _recipient_dict(r: CampaignRecipient):
    return {
        'id': r.id,
        'nome': r.nome,
        'telefone': r.telefone,
        'telegram': bool(r.telegram_chat_id),
        'origem': r.origem,
        'status': r.status,
        'erro': r.erro,
        'selecionado': not (r.status == 'ignorado' and r.erro == NAO_SELECIONADO),
        'enviado_em': r.enviado_em.isoformat() if r.enviado_em else None,
    }


def _keep_publico(c: Campaign, origem: str):
    """Campanha agendada só para outra origem: os recém-adicionados também ficam fora."""
    publico = _publico(_counts([c.id])[c.id])
    if publico not in ('todos', origem):
        c.destinatarios.filter(status='pendente', origem=origem).update(status='ignorado', erro=FORA_DO_PUBLICO)


def _existing_keys(c: Campaign, origem: str):
    rows = c.destinatarios.filter(origem=origem).values_list('telefone', 'telegram_chat_id')
    return {tg or tel for tel, tg in rows}


def _is_telegram(c: Campaign):
    return bool(c.canal_id) and c.canal.tipo == 'telegram'


def _contact_key(contact, telegram: bool):
    """Telefone (ou chat do Telegram) que identifica o contato como destinatário; '' se não serve."""
    if telegram:
        attrs = contact.additional_attributes or {}
        return str(attrs.get('telegram_chat_id') or attrs.get('telegram_user_id') or '').strip()
    phone = normalize_whatsapp_phone(contact.phone)
    return phone if is_valid_whatsapp_phone(phone) else ''


def _contact_keys(c: Campaign, ids):
    from conversations.models import Contact

    telegram = _is_telegram(c)
    qs = Contact.objects.filter(provedor_id=c.provedor_id, pk__in=ids).only('id', 'phone', 'additional_attributes')
    return {contact.id: _contact_key(contact, telegram) for contact in qs}


def _busca_contatos(qs, busca: str):
    busca = (busca or '').strip()
    if not busca:
        return qs
    return qs.filter(Q(name__icontains=busca) | Q(phone__icontains=busca) | Q(email__icontains=busca))


def _contatos_disponiveis(c: Campaign, busca: str):
    """{id: chave} dos contatos que podem receber (não bloqueados, com telefone/chat válido)."""
    from conversations.models import Contact

    telegram = _is_telegram(c)
    qs = _busca_contatos(Contact.objects.filter(provedor_id=c.provedor_id, bloqueado_disparos=False), busca)
    chaves = {}
    for contact in qs.only('id', 'phone', 'additional_attributes').iterator():
        key = _contact_key(contact, telegram)
        if key:
            chaves[contact.id] = key
    return chaves


def _alvo_contatos(c: Campaign, chaves):
    keys = {k for k in chaves.values() if k}
    alvo = Q(contato_id__in=list(chaves))
    if keys:
        alvo |= Q(telegram_chat_id__in=keys) if _is_telegram(c) else Q(telefone__in=keys)
    return alvo


def _contatos_na_campanha(c: Campaign, ids):
    """Ids dos contatos do sistema que já estão na campanha (a lista importada é separada)."""
    presentes = set(
        c.destinatarios.filter(origem='contato', contato_id__in=ids).values_list('contato_id', flat=True)
    )
    keys = _existing_keys(c, 'contato')
    for contact_id, key in _contact_keys(c, ids).items():
        if key and key in keys:
            presentes.add(contact_id)
    return presentes


def _parse_ids(values):
    if isinstance(values, str):
        values = values.split(',')
    return [int(i) for i in (values or []) if str(i).strip().isdigit()]


def _add_from_contacts(c: Campaign, data):
    from conversations.models import Contact

    qs = Contact.objects.filter(provedor_id=c.provedor_id, bloqueado_disparos=False)
    if data.get('todos'):
        qs = _busca_contatos(qs, str(data.get('busca') or ''))
    else:
        ids = [int(i) for i in (data.get('contato_ids') or []) if str(i).isdigit()]
        if not ids:
            return None, 'Selecione ao menos um contato.'
        qs = qs.filter(pk__in=ids)

    telegram = c.canal.tipo == 'telegram'
    keys = _existing_keys(c, 'contato')
    novos, sem_canal = [], 0
    for contact in qs.only('id', 'name', 'phone', 'additional_attributes').iterator():
        attrs = contact.additional_attributes or {}
        tg = str(attrs.get('telegram_chat_id') or attrs.get('telegram_user_id') or '').strip()
        phone = normalize_whatsapp_phone(contact.phone)
        if telegram and not tg:
            sem_canal += 1
            continue
        if not telegram and not is_valid_whatsapp_phone(phone):
            sem_canal += 1
            continue
        key = tg if telegram else phone
        if key in keys:
            continue
        keys.add(key)
        novos.append(CampaignRecipient(
            campanha=c, contato=contact, nome=(contact.name or '')[:255],
            telefone=phone if is_valid_whatsapp_phone(phone) else '',
            telegram_chat_id=tg if telegram else '', origem='contato',
        ))
    CampaignRecipient.objects.bulk_create(novos, batch_size=500)
    if novos:
        _keep_publico(c, 'contato')
    motivo = 'sem conversa no Telegram' if telegram else 'sem telefone válido'
    return {'adicionados': len(novos), 'ignorados': sem_canal, 'motivo_ignorados': motivo}, None


@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def recipients(request, pk):
    provedor_id, err = _context(request)
    if err:
        return err
    c = _get_campaign(provedor_id, pk)
    if c is None:
        return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        if 'contatos' in request.query_params:
            ids = _parse_ids(request.query_params.get('contatos'))[:200]
            disponiveis = _contatos_disponiveis(c, request.query_params.get('busca'))
            keys = _existing_keys(c, 'contato')
            marcados = sum(1 for k in disponiveis.values() if k in keys)
            return Response({
                'contato_ids': sorted(_contatos_na_campanha(c, ids)) if ids else [],
                'disponiveis': len(disponiveis),
                'marcados': marcados,
                'todos_marcados': bool(disponiveis) and marcados == len(disponiveis),
            })
        qs = c.destinatarios.all()
        st = request.query_params.get('status')
        if st in STATUS_DESTINATARIO:
            qs = qs.filter(status=st)
        origem = request.query_params.get('origem')
        if origem in ORIGENS:
            qs = qs.filter(origem=origem)
        busca = (request.query_params.get('busca') or '').strip()
        if busca:
            qs = qs.filter(Q(nome__icontains=busca) | Q(telefone__icontains=busca))
        try:
            page = max(int(request.query_params.get('page') or 1), 1)
        except ValueError:
            page = 1
        size = 50
        total = qs.count()
        items = qs.order_by('id')[(page - 1) * size: page * size]
        return Response({'count': total, 'page': page, 'page_size': size,
                         'results': [_recipient_dict(r) for r in items]})

    if c.status not in EDITAVEIS:
        return _bad('Só é possível alterar destinatários de campanhas em rascunho ou agendadas.')

    data = request.data if isinstance(request.data, dict) else {}

    if request.method == 'PATCH':
        qs = c.destinatarios.filter(origem='csv').filter(
            Q(status='pendente') | Q(status='ignorado', erro__in=(FORA_DO_PUBLICO, NAO_SELECIONADO))
        )
        if not data.get('todos'):
            qs = qs.filter(pk__in=_parse_ids(data.get('ids')))
        if data.get('selecionado'):
            alterados = qs.filter(status='ignorado', erro=NAO_SELECIONADO).update(status='pendente', erro='')
            if alterados:
                _keep_publico(c, 'csv')
        else:
            alterados = qs.exclude(status='ignorado', erro=NAO_SELECIONADO).update(
                status='ignorado', erro=NAO_SELECIONADO
            )
        return Response({'alterados': alterados, 'contagem': _counts([c.id])[c.id]})

    if request.method == 'DELETE':
        qs = c.destinatarios.all()
        if data.get('contato_ids'):
            chaves = _contact_keys(c, _parse_ids(data.get('contato_ids')))
            qs = qs.filter(origem='contato').filter(_alvo_contatos(c, chaves))
        elif data.get('todos'):
            if data.get('origem') in ORIGENS:
                qs = qs.filter(origem=data['origem'])
            busca = str(data.get('busca') or '').strip()
            if data.get('origem') == 'contato' and busca:
                qs = qs.filter(_alvo_contatos(c, _contatos_disponiveis(c, busca)))
        else:
            qs = qs.filter(pk__in=_parse_ids(data.get('ids')))
        removidos, _ = qs.delete()
        return Response({'removidos': removidos, 'contagem': _counts([c.id])[c.id]})

    result, error = _add_from_contacts(c, request.data)
    if error:
        return _bad(error)
    return Response({**result, 'contagem': _counts([c.id])[c.id]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def recipients_csv(request, pk):
    provedor_id, err = _context(request)
    if err:
        return err
    c = _get_campaign(provedor_id, pk)
    if c is None:
        return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)
    if c.status not in EDITAVEIS:
        return _bad('Só é possível alterar destinatários de campanhas em rascunho ou agendadas.')
    if c.canal and c.canal.tipo == 'telegram':
        return _bad('No Telegram só é possível enviar para contatos que já conversaram com o canal.')
    upload = request.FILES.get('file')
    if not upload:
        return _bad('Envie o arquivo CSV.')
    if upload.size > MAX_CSV_BYTES:
        return _bad('O CSV deve ter no máximo 5 MB.')
    try:
        rows, resumo = parse_recipients_csv(upload.read())
    except ValueError as exc:
        return _bad(str(exc))

    from conversations.models import Contact

    phones = [row['telefone'] for row in rows]
    bloqueados = set(
        Contact.objects.filter(provedor_id=provedor_id, phone__in=phones, bloqueado_disparos=True)
        .values_list('phone', flat=True)
    )
    contatos = {
        phone: (cid, name)
        for phone, cid, name in Contact.objects.filter(provedor_id=provedor_id, phone__in=phones)
        .values_list('phone', 'id', 'name')
    }
    keys = _existing_keys(c, 'csv')
    novos = []
    for row in rows:
        if row['telefone'] in keys or row['telefone'] in bloqueados:
            continue
        keys.add(row['telefone'])
        contato_id, contato_nome = contatos.get(row['telefone'], (None, ''))
        nome = row['nome'] or ('' if (contato_nome or '').strip() == 'Sem nome' else (contato_nome or '').strip())
        novos.append(CampaignRecipient(
            campanha=c, contato_id=contato_id, nome=nome[:255],
            telefone=row['telefone'], dados=row['dados'], origem='csv',
        ))
    CampaignRecipient.objects.bulk_create(novos, batch_size=500)
    if novos:
        _keep_publico(c, 'csv')
    return Response({
        'adicionados': len(novos),
        'bloqueados': len(bloqueados),
        **resumo,
        'contagem': _counts([c.id])[c.id],
    })


HEADER_FILE_RULES = {
    'IMAGE': ({'.jpg', '.jpeg', '.png'}, 5 * 1024 * 1024, 'imagem JPG ou PNG de até 5 MB'),
    'VIDEO': ({'.mp4', '.3gp'}, 16 * 1024 * 1024, 'vídeo MP4 de até 16 MB'),
    'DOCUMENT': ({'.pdf'}, 20 * 1024 * 1024, 'PDF de até 20 MB'),
}


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def header_file(request, pk):
    """Arquivo do cabeçalho do template (imagem/vídeo/PDF) enviado do computador."""
    provedor_id, err = _context(request)
    if err:
        return err
    c = _get_campaign(provedor_id, pk)
    if c is None:
        return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        if not c.template_header_arquivo:
            return _bad('Campanha sem arquivo no cabeçalho', status.HTTP_404_NOT_FOUND)
        try:
            return FileResponse(c.template_header_arquivo.open('rb'))
        except (FileNotFoundError, ValueError):
            return _bad('Arquivo não encontrado no servidor', status.HTTP_404_NOT_FOUND)

    if c.status not in EDITAVEIS:
        return _bad('Só é possível alterar campanhas em rascunho ou agendadas.')

    if request.method == 'DELETE':
        _clear_header_file(c)
        c.save()
        return Response(_campaign_dict(c))

    req = service.template_requirements(c.template_def) if c.template_def else {}
    rule = HEADER_FILE_RULES.get(req.get('header_format'))
    if not rule:
        return _bad('O template escolhido não tem imagem, vídeo ou documento no cabeçalho.')
    upload = request.FILES.get('file')
    if not upload:
        return _bad('Envie o arquivo.')
    extensoes, limite, descricao = rule
    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext not in extensoes or upload.size > limite:
        return _bad(f'Arquivo inválido: o cabeçalho deste template aceita {descricao}.')

    _clear_header_file(c)
    c.template_header_url = ''
    c.template_header_arquivo.save(f'campanha_{c.id}{ext}', upload, save=False)
    c.save()
    return Response(_campaign_dict(c))


def _parse_schedule(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dispatch(request, pk):
    provedor_id, err = _context(request)
    if err:
        return err
    with transaction.atomic():
        c = Campaign.objects.select_for_update(of=('self',)).select_related('canal', 'provedor').filter(
            pk=pk, provedor_id=provedor_id
        ).first()
        if c is None:
            return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)
        if c.status not in EDITAVEIS:
            return _bad('Esta campanha já foi disparada.')
        problema = service.channel_issue(c.canal)
        if problema:
            return _bad(problema)
        error = _apply_payload(c, {}, provedor_id, strict=True)
        if error:
            return _bad(error)
        publico = str(request.data.get('publico') or 'todos')
        if publico not in PUBLICOS:
            return _bad('Público inválido.')
        elegiveis = c.destinatarios.filter(Q(status='pendente') | Q(status='ignorado', erro=FORA_DO_PUBLICO))
        if not elegiveis.exists():
            return _bad('Adicione destinatários antes de disparar.')
        if publico != 'todos' and not elegiveis.filter(origem=publico).exists():
            return _bad('Não há destinatários pendentes ' + (
                'importados do CSV.' if publico == 'csv' else 'vindos dos contatos no sistema.'
            ))
        modo = str(request.data.get('modo') or 'agora')
        if modo == 'agendar':
            quando = _parse_schedule(request.data.get('agendada_para'))
            if quando is None:
                return _bad('Informe o dia e o horário do disparo.')
            if quando <= timezone.now() + timedelta(seconds=30):
                return _bad('Escolha um horário no futuro.')

        c.destinatarios.filter(status='ignorado', erro=FORA_DO_PUBLICO).update(status='pendente', erro='')
        if publico != 'todos':
            c.destinatarios.filter(status='pendente').exclude(origem=publico).update(
                status='ignorado', erro=FORA_DO_PUBLICO
            )
        c.erro = ''
        if modo == 'agendar':
            c.status, c.agendada_para = 'agendada', quando
            c.save()
        else:
            c.status, c.agendada_para, c.iniciada_em = 'enviando', None, timezone.now()
            c.save()
            service.start_after_commit(c.id)
    return Response(_campaign_dict(c))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel(request, pk):
    provedor_id, err = _context(request)
    if err:
        return err
    c = _get_campaign(provedor_id, pk)
    if c is None:
        return _bad('Campanha não encontrada', status.HTTP_404_NOT_FOUND)
    if c.status not in ('agendada', 'enviando'):
        return _bad('Só é possível cancelar campanhas agendadas ou em envio.')
    Campaign.objects.filter(pk=c.id).update(status='cancelada', concluida_em=timezone.now())
    c.refresh_from_db()
    return Response(_campaign_dict(c))
