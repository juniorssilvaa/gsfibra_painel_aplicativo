import json
import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from datetime import datetime

logger = logging.getLogger(__name__)

def verificar_horario_atendimento(provedor) -> Dict[str, Any]:
    """
    Verifica se o provedor está dentro do horário de atendimento.
    Garante o uso do fuso horário correto (America/Belem).
    
    Retorna: {
        'dentro_horario': bool,
        'proximo_horario': str ou None,
        'mensagem': str ou None,
        'horarios_completos': list
    }
    """
    try:
        if not provedor or not provedor.horarios_atendimento:
            return {
                'dentro_horario': True,
                'proximo_horario': None,
                'mensagem': None,
                'horarios_completos': []
            }
        
        # Parsear horários (JSON ou List)
        horarios = provedor.horarios_atendimento
        if isinstance(horarios, str):
            try:
                horarios = json.loads(horarios)
            except:
                return {'dentro_horario': True, 'proximo_horario': None, 'mensagem': None, 'horarios_completos': []}
        
        if not isinstance(horarios, list):
            return {'dentro_horario': True, 'proximo_horario': None, 'mensagem': None, 'horarios_completos': []}

        # 🚨 CORREÇÃO DE TIMEZONE: Usar localtime para respeitar America/Belem configurado no Django
        now = timezone.localtime(timezone.now())
        dia_atual_num = now.weekday()  # 0=Segunda, 6=Domingo
        dias_semana = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
        dia_atual_nome = dias_semana[dia_atual_num]
        
        # Buscar horários do dia atual
        horario_hoje = next((d for d in horarios if d.get('dia') == dia_atual_nome), None)
        
        # 1. Verificar se hoje está fechado ou sem períodos
        if not horario_hoje or not horario_hoje.get('periodos'):
            return _buscar_proximo_horario_disponivel(horarios, dia_atual_num, dias_semana)

        # 2. Verificar períodos de hoje
        periodos = horario_hoje.get('periodos', [])
        hora_atual_minutos = now.hour * 60 + now.minute
        
        for p in periodos:
            try:
                h_ini, m_ini = map(int, p.get('inicio', '00:00').split(':'))
                h_fim, m_fim = map(int, p.get('fim', '00:00').split(':'))
                
                inicio_minutos = h_ini * 60 + m_ini
                fim_minutos = h_fim * 60 + m_fim
                
                if inicio_minutos <= hora_atual_minutos <= fim_minutos:
                    return {
                        'dentro_horario': True,
                        'proximo_horario': None,
                        'mensagem': None,
                        'horarios_completos': horarios
                    }
            except:
                continue

        # 3. Se não está em nenhum periodo agora, ver se ainda abre hoje
        for p in periodos:
            try:
                h_ini, m_ini = map(int, p.get('inicio', '00:00').split(':'))
                inicio_minutos = h_ini * 60 + m_ini
                if hora_atual_minutos < inicio_minutos:
                    return {
                        'dentro_horario': False,
                        'proximo_horario': f"hoje às {p.get('inicio')}",
                        'mensagem': f"Você será atendido hoje às {p.get('inicio')}",
                        'horarios_completos': horarios
                    }
            except:
                continue

        # 4. Caso contrário, buscar o próximo dia disponível
        return _buscar_proximo_horario_disponivel(horarios, dia_atual_num, dias_semana)

    except Exception as e:
        logger.error(f"Erro ao verificar horário: {e}")
        return {'dentro_horario': True, 'proximo_horario': None, 'mensagem': None, 'horarios_completos': []}

def _buscar_proximo_horario_disponivel(horarios, dia_atual_num, dias_semana) -> Dict[str, Any]:
    """Helper para buscar o próximo dia e hora em que a empresa abrirá."""
    for i in range(1, 8):
        prox_dia_num = (dia_atual_num + i) % 7
        prox_dia_nome = dias_semana[prox_dia_num]
        dia_info = next((d for d in horarios if d.get('dia') == prox_dia_nome and d.get('periodos')), None)
        
        if dia_info and dia_info['periodos']:
            inicio = dia_info['periodos'][0].get('inicio', '')
            return {
                'dentro_horario': False,
                'proximo_horario': f"{prox_dia_nome} às {inicio}",
                'mensagem': f"Você será atendido na {prox_dia_nome} às {inicio}",
                'horarios_completos': horarios
            }
            
    return {
        'dentro_horario': False, 
        'proximo_horario': "no próximo dia útil", 
        'mensagem': "Fora do horário de atendimento.",
        'horarios_completos': horarios
    }
