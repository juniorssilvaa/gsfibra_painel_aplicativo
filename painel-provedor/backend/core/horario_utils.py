import json
import logging
from typing import Any, Dict, List, Optional, Union

from django.utils import timezone

logger = logging.getLogger(__name__)

DIAS_SEMANA = [
    'Segunda-feira',
    'Terça-feira',
    'Quarta-feira',
    'Quinta-feira',
    'Sexta-feira',
    'Sábado',
    'Domingo',
]


def parse_horarios_atendimento(raw: Union[str, list, None]) -> List[Dict[str, Any]]:
    """Normaliza horários salvos como JSON string ou lista."""
    if not raw:
        return []
    horarios = raw
    if isinstance(horarios, str):
        try:
            horarios = json.loads(horarios)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(horarios, list):
        return []
    return horarios


def parse_feriados_atendimento(raw: Union[str, list, None]) -> List[Dict[str, Any]]:
    """Normaliza feriados salvos como JSON string ou lista."""
    if not raw:
        return []
    feriados = raw
    if isinstance(feriados, str):
        try:
            feriados = json.loads(feriados)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(feriados, list):
        return []
    return [item for item in feriados if isinstance(item, dict)]


def _hora_para_minutos(value: Union[str, None]) -> Optional[int]:
    """Converte HH:MM em minutos desde meia-noite."""
    if not value or not str(value).strip():
        return None
    try:
        parts = str(value).strip().split(':')
        hora = int(parts[0])
        minuto = int(parts[1]) if len(parts) > 1 else 0
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            return hora * 60 + minuto
    except (ValueError, TypeError, IndexError):
        return None
    return None


def _feriado_dia_inteiro(item: Dict[str, Any]) -> bool:
    """Feriados antigos sem campo all_day continuam valendo o dia todo."""
    if 'all_day' in item:
        return bool(item.get('all_day'))
    return not (item.get('start_time') or item.get('end_time'))


def feriado_hoje(provedor) -> Optional[Dict[str, Any]]:
    """Retorna feriado ativo agora, respeitando janela de horário quando configurada.

    Prioridade: feriados/datas especiais do provedor; depois feriados nacionais ativos.
    """
    if not provedor:
        return None

    now = timezone.localtime(timezone.now())
    hoje_date = now.date()
    hoje = hoje_date.isoformat()
    hora_atual_minutos = now.hour * 60 + now.minute

    for item in parse_feriados_atendimento(getattr(provedor, 'attendance_holidays', None)):
        # Feriados nacionais embutidos por engano na lista custom não se aplicam aqui
        if item.get('source') == 'national' or item.get('locked'):
            continue
        data = str(item.get('date') or '').strip()
        ativo = item.get('active', True)
        if ativo is False:
            continue
        if data != hoje:
            continue

        if _feriado_dia_inteiro(item):
            return item

        inicio_minutos = _hora_para_minutos(item.get('start_time') or '00:00')
        fim_minutos = _hora_para_minutos(item.get('end_time') or '23:59')
        if inicio_minutos is None:
            inicio_minutos = 0
        if fim_minutos is None:
            fim_minutos = 23 * 60 + 59
        if fim_minutos == 0 and inicio_minutos > 0:
            fim_minutos = 24 * 60

        if inicio_minutos <= hora_atual_minutos <= fim_minutos:
            return item

    from .national_holidays import national_holiday_on_date

    return national_holiday_on_date(
        getattr(provedor, 'attendance_national_holidays', None),
        hoje_date,
    )


def horarios_efetivos_equipe(team) -> List[Dict[str, Any]]:
    """Horários da equipe ou fallback para o provedor."""
    if not team:
        return []
    team_horarios = parse_horarios_atendimento(getattr(team, 'horarios_atendimento', None))
    if team_horarios:
        return team_horarios
    provedor = getattr(team, 'provedor', None)
    if provedor:
        return parse_horarios_atendimento(getattr(provedor, 'horarios_atendimento', None))
    return []


def formatar_aviso_transferencia_fora_horario(
    horario_info: Optional[Dict[str, Any]],
    setor: Optional[str] = None,
) -> str:
    """
    Texto ao cliente na transferência quando a equipe humana está fechada.
    Em feriado, inclui o motivo (nome do feriado) e o próximo horário comercial.
    """
    if not horario_info or horario_info.get('dentro_horario'):
        return ''

    setor_txt = f' de *{setor}*' if setor else ''
    proximo = (horario_info.get('proximo_horario') or '').strip() or None
    feriado = horario_info.get('feriado') if isinstance(horario_info.get('feriado'), dict) else None
    nome_feriado = ''
    if horario_info.get('fonte') == 'feriado' and feriado:
        nome_feriado = str(feriado.get('name') or '').strip()

    if nome_feriado:
        if proximo:
            return (
                f'\n\nDevido ao feriado *{nome_feriado}*, nossa equipe{setor_txt} '
                f'falará com você a partir de *{proximo}*.'
            )
        return (
            f'\n\nDevido ao feriado *{nome_feriado}*, estamos fora do horário de atendimento. '
            f'Nossa equipe{setor_txt} falará com você assim que possível.'
        )

    if proximo:
        return (
            f'\n\nComo estamos fora do nosso horário de atendimento agora, '
            f'nossa equipe{setor_txt} falará com você a partir de *{proximo}*.'
        )
    return (
        f'\n\nComo estamos fora do nosso horário de atendimento agora, '
        f'nossa equipe{setor_txt} falará com você assim que possível.'
    )


def _proximo_horario_apos_feriado(
    horarios: List[Dict[str, Any]],
    feriado: Dict[str, Any],
    now,
) -> Dict[str, Any]:
    """Próximo atendimento após o feriado (retoma no dia se parcial, senão próximo dia útil)."""
    dia_atual_num = now.weekday()

    if not _feriado_dia_inteiro(feriado):
        fim_min = _hora_para_minutos(feriado.get('end_time') or '23:59')
        if fim_min is None:
            fim_min = 23 * 60 + 59
        if fim_min == 0:
            fim_min = 24 * 60

        dia_atual_nome = DIAS_SEMANA[dia_atual_num]
        horario_hoje = next((d for d in horarios if d.get('dia') == dia_atual_nome), None)
        periodos = (horario_hoje or {}).get('periodos') or []
        for p in periodos:
            try:
                h_ini, m_ini = map(int, str(p.get('inicio', '00:00')).split(':'))
                h_fim, m_fim = map(int, str(p.get('fim', '00:00')).split(':'))
                inicio_minutos = h_ini * 60 + m_ini
                fim_periodo = h_fim * 60 + m_fim
                if fim_periodo == 0 and inicio_minutos > 0:
                    fim_periodo = 24 * 60
                if fim_min < fim_periodo:
                    retoma = max(fim_min, inicio_minutos)
                    if retoma < fim_periodo:
                        hh, mm = divmod(retoma, 60)
                        hora_txt = f'{hh:02d}:{mm:02d}'
                        return {
                            'dentro_horario': False,
                            'proximo_horario': f'hoje às {hora_txt}',
                            'mensagem': f'Você será atendido hoje às {hora_txt}',
                            'horarios_completos': horarios,
                        }
            except (ValueError, TypeError):
                continue

    return _buscar_proximo_horario_disponivel(horarios, dia_atual_num, DIAS_SEMANA)


def verificar_horario_atendimento(provedor, team=None, considerar_feriados: bool = True) -> Dict[str, Any]:
    """
    Verifica se está dentro do horário de atendimento.

    Se `team` tiver horário próprio, usa a equipe; senão usa o horário global do provedor.
    Sem horário configurado, considera sempre aberto.

    Retorna: {
        'dentro_horario': bool,
        'proximo_horario': str ou None,
        'mensagem': str ou None,
        'horarios_completos': list,
        'fonte': 'equipe' | 'provedor' | 'aberto' | 'feriado',
        'feriado': dict ou None,
    }
    """
    try:
        horarios: List[Dict[str, Any]] = []
        fonte = 'aberto'

        if team is not None:
            team_horarios = parse_horarios_atendimento(getattr(team, 'horarios_atendimento', None))
            if team_horarios:
                horarios = team_horarios
                fonte = 'equipe'
            elif provedor and provedor.horarios_atendimento:
                horarios = parse_horarios_atendimento(provedor.horarios_atendimento)
                fonte = 'provedor'
        elif provedor and provedor.horarios_atendimento:
            horarios = parse_horarios_atendimento(provedor.horarios_atendimento)
            fonte = 'provedor'

        now = timezone.localtime(timezone.now())
        feriado = feriado_hoje(provedor) if considerar_feriados else None

        if feriado:
            result = _proximo_horario_apos_feriado(horarios, feriado, now)
            result['fonte'] = 'feriado'
            result['feriado'] = feriado
            nome_feriado = str(feriado.get('name') or 'feriado').strip()
            proximo = result.get('proximo_horario')
            if _feriado_dia_inteiro(feriado):
                mensagem_feriado = (
                    f'Devido ao feriado {nome_feriado}, você será atendido a partir de {proximo}.'
                    if proximo
                    else f'Devido ao feriado {nome_feriado}, estamos fora do horário de atendimento.'
                )
            else:
                inicio = str(feriado.get('start_time') or '').strip()
                fim = str(feriado.get('end_time') or '').strip()
                periodo = f' das {inicio}' + (f' às {fim}' if fim else '')
                mensagem_feriado = (
                    f'Devido ao feriado {nome_feriado}{periodo}, você será atendido a partir de {proximo}.'
                    if proximo
                    else f'Devido ao feriado {nome_feriado}{periodo}, estamos fora do horário de atendimento.'
                )
            result['mensagem'] = mensagem_feriado
            return result

        if not horarios:
            return {
                'dentro_horario': True,
                'proximo_horario': None,
                'mensagem': None,
                'horarios_completos': [],
                'fonte': fonte,
                'feriado': None,
            }

        dia_atual_num = now.weekday()
        dia_atual_nome = DIAS_SEMANA[dia_atual_num]

        horario_hoje = next((d for d in horarios if d.get('dia') == dia_atual_nome), None)

        if not horario_hoje or not horario_hoje.get('periodos'):
            result = _buscar_proximo_horario_disponivel(horarios, dia_atual_num, DIAS_SEMANA)
            result['fonte'] = fonte
            result['feriado'] = None
            return result

        periodos = horario_hoje.get('periodos', [])
        hora_atual_minutos = now.hour * 60 + now.minute

        for p in periodos:
            try:
                h_ini, m_ini = map(int, p.get('inicio', '00:00').split(':'))
                h_fim, m_fim = map(int, p.get('fim', '00:00').split(':'))
                inicio_minutos = h_ini * 60 + m_ini
                fim_minutos = h_fim * 60 + m_fim
                # 00:00 como fim = meia-noite (fim do dia), não início do dia
                if fim_minutos == 0 and inicio_minutos > 0:
                    fim_minutos = 24 * 60
                if inicio_minutos <= hora_atual_minutos <= fim_minutos:
                    return {
                        'dentro_horario': True,
                        'proximo_horario': None,
                        'mensagem': None,
                        'horarios_completos': horarios,
                        'fonte': fonte,
                        'feriado': None,
                    }
            except (ValueError, TypeError):
                continue

        for p in periodos:
            try:
                h_ini, m_ini = map(int, p.get('inicio', '00:00').split(':'))
                inicio_minutos = h_ini * 60 + m_ini
                if hora_atual_minutos < inicio_minutos:
                    return {
                        'dentro_horario': False,
                        'proximo_horario': f"hoje às {p.get('inicio')}",
                        'mensagem': f"Você será atendido hoje às {p.get('inicio')}",
                        'horarios_completos': horarios,
                        'fonte': fonte,
                        'feriado': None,
                    }
            except (ValueError, TypeError):
                continue

        result = _buscar_proximo_horario_disponivel(horarios, dia_atual_num, DIAS_SEMANA)
        result['fonte'] = fonte
        result['feriado'] = None
        return result

    except Exception as e:
        logger.error('Erro ao verificar horário: %s', e)
        return {
            'dentro_horario': True,
            'proximo_horario': None,
            'mensagem': None,
            'horarios_completos': [],
            'fonte': 'aberto',
            'feriado': None,
        }


def verificar_automacao_agendada(provedor) -> Dict[str, Any]:
    """Define se a automação (IA/chatbot) deve ficar ativa agora."""
    if not provedor:
        return {'ativa': True, 'motivo': 'provedor_ausente'}

    if not getattr(provedor, 'automation_schedule_enabled', False):
        return {'ativa': True, 'motivo': 'agendamento_desativado'}

    modo = (getattr(provedor, 'automation_schedule_mode', None) or 'outside_business_hours').strip().lower()
    considerar_feriados = bool(getattr(provedor, 'automation_schedule_apply_holidays', True))
    horario_info = verificar_horario_atendimento(
        provedor,
        considerar_feriados=considerar_feriados,
    )
    dentro_horario = bool(horario_info.get('dentro_horario'))

    if modo == 'inside_business_hours':
        ativa = dentro_horario
    else:
        ativa = not dentro_horario

    fallback_team = getattr(provedor, 'automation_schedule_fallback_team', None)
    return {
        'ativa': ativa,
        'modo': modo,
        'motivo': 'dentro_horario' if dentro_horario else 'fora_horario',
        'horario_info': horario_info,
        'fallback_team_id': getattr(fallback_team, 'id', None) or getattr(
            provedor, 'automation_schedule_fallback_team_id', None
        ),
    }


def _buscar_proximo_horario_disponivel(
    horarios: List[Dict[str, Any]],
    dia_atual_num: int,
    dias_semana: List[str],
) -> Dict[str, Any]:
    """Busca o próximo dia e hora em que haverá atendimento."""
    for i in range(1, 8):
        prox_dia_num = (dia_atual_num + i) % 7
        prox_dia_nome = dias_semana[prox_dia_num]
        dia_info = next(
            (d for d in horarios if d.get('dia') == prox_dia_nome and d.get('periodos')),
            None,
        )
        if dia_info and dia_info['periodos']:
            inicio = dia_info['periodos'][0].get('inicio', '')
            return {
                'dentro_horario': False,
                'proximo_horario': f'{prox_dia_nome} às {inicio}',
                'mensagem': f'Você será atendido na {prox_dia_nome} às {inicio}',
                'horarios_completos': horarios,
            }

    return {
        'dentro_horario': False,
        'proximo_horario': 'no próximo dia útil',
        'mensagem': 'Fora do horário de atendimento.',
        'horarios_completos': horarios,
    }
