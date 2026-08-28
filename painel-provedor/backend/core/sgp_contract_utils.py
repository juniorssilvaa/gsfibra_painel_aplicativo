"""Helpers para status de contrato SGP (suspenso, etc.)."""


def get_contrato_id(contrato: dict | None) -> str | None:
    if not contrato or not isinstance(contrato, dict):
        return None
    for key in ('contratoId', 'id', 'id_contrato', 'contrato_id', 'codigo'):
        val = contrato.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def get_plano_nome(contrato: dict | None) -> str:
    if not contrato or not isinstance(contrato, dict):
        return ''
    for key in (
        'plano_nome',
        'servico_plano',
        'planointernet',
        'planoInternet',
        'nomePlano',
        'nome_plano',
        'plano',
        'servico',
    ):
        val = contrato.get(key)
        if val is not None and str(val).strip() and not isinstance(val, dict):
            return str(val).strip()
    plano = contrato.get('plano')
    if isinstance(plano, dict):
        nested = get_plano_nome(plano) or (plano.get('nome') or plano.get('descricao') or '')
        if nested:
            return str(nested).strip()
    return ''


def normalize_verifica_acesso(resp) -> dict:
    """
    Normaliza POST /api/ura/verificaacesso/ para uso no painel.
    SGP: status=1 online, status=9 manutenção, lista vazia ou outro = offline.
    """
    if resp is None:
        return {'connection': 'unknown', 'label': 'Indisponível'}

    if isinstance(resp, list):
        if resp:
            return {'connection': 'online', 'label': 'Serviço Online', 'raw': resp}
        return {'connection': 'offline', 'label': 'Offline', 'raw': resp}

    if not isinstance(resp, dict):
        return {'connection': 'unknown', 'label': 'Indisponível', 'raw': resp}

    status = resp.get('status', resp.get('status_conexao'))

    if status == 9 or str(status).upper() in ('9', 'MANUTENCAO', 'MANUTENÇÃO'):
        return {
            'connection': 'manutencao',
            'label': 'Manutenção',
            'protocolo': resp.get('protocolo'),
            'tempo': resp.get('tempo'),
            'raw': resp,
        }
    if status == 1 or str(status).lower() in ('1', 'online', 'ativo', 'connected', 'true'):
        return {'connection': 'online', 'label': 'Serviço Online', 'raw': resp}

    status_str = str(status or '').lower()
    if 'online' in status_str or status_str == 'true':
        return {'connection': 'online', 'label': 'Serviço Online', 'raw': resp}
    if status in (0, '0') or 'offline' in status_str:
        return {'connection': 'offline', 'label': 'Offline', 'raw': resp}

    return {'connection': 'offline', 'label': 'Offline', 'raw': resp}


def contrato_dict_is_suspenso(contrato: dict | None) -> bool:
    if not contrato or not isinstance(contrato, dict):
        return False

    display = str(contrato.get('contratoStatusDisplay') or '').strip().lower()
    if display in ('suspenso', 'suspensa'):
        return True

    status_raw = str(contrato.get('contratoStatus') or '').strip()
    if status_raw == '4':
        return True
    if 'SUSPENS' in status_raw.upper():
        return True
    return False


def flow_context_is_suspenso(flow_context: dict | None) -> bool:
    if not flow_context:
        return False
    if flow_context.get('is_suspenso') is True:
        return True

    display = str(flow_context.get('contrato_status_display') or '').upper()
    if 'SUSPENS' in display:
        return True

    status = str(flow_context.get('status_contrato') or '')
    if status == '4' or 'SUSPENS' in status.upper():
        return True
    return False


def provedor_allows_ticket_when_suspended(provedor) -> bool:
    return bool(getattr(provedor, 'allow_ticket_when_contract_suspended', False))


def default_blocked_ticket_message() -> str:
    return (
        'Seu contrato está atualmente *suspenso*. '
        'Não é possível abrir chamados técnicos nessa situação.'
    )


def provedor_sends_financial_menu_after_suspended_block(provedor) -> bool:
    return bool(getattr(provedor, 'send_financial_menu_after_suspended_block', False))


_FINANCIAL_SGP_ACTIONS = frozenset({'listar_titulos', 'liberar_por_confianca'})
_FINANCIAL_KEYWORDS = (
    'financeiro', 'fatura', 'boleto', 'pix', 'pagamento', 'cobrança', 'cobranca',
    'segunda via', '2 via', '2ª via', '2a via', 'titulo', 'título', 'vencimento',
    'liberação', 'liberacao', 'confiança', 'confianca', 'desbloqueio',
)


def _text_has_financial_keyword(text: str) -> bool:
    lowered = (text or '').lower()
    return any(kw in lowered for kw in _FINANCIAL_KEYWORDS)


def _node_financial_score(node: dict, nodes_by_id: dict, edges: list) -> int:
    """Pontua quão provável um nó menu é o menu financeiro do fluxo."""
    if not node or node.get('type') != 'menu':
        return 0

    data = node.get('data') or {}
    score = 0
    blob_parts = [
        str(data.get('content') or ''),
        str(data.get('headerText') or data.get('header') or ''),
        str(data.get('sectionTitle') or ''),
    ]
    for row in data.get('rows') or []:
        blob_parts.extend([
            str(row.get('title') or ''),
            str(row.get('description') or ''),
        ])
    blob = ' '.join(blob_parts)
    if _text_has_financial_keyword(blob):
        score += 3

    node_id = node.get('id')
    for edge in edges or []:
        if edge.get('source') != node_id:
            continue
        target = nodes_by_id.get(edge.get('target'))
        if not target or target.get('type') != 'sgp':
            continue
        action = (target.get('data') or {}).get('sgpAction', '')
        if action in _FINANCIAL_SGP_ACTIONS:
            score += 5

    return score


def find_financial_menu_node(flow) -> dict | None:
    """
    Localiza o nó de menu financeiro no fluxo ativo (2ª via, liberação, etc.).
    Retorna o nó com maior pontuação ou None.
    """
    nodes = getattr(flow, 'nodes', None) or []
    edges = getattr(flow, 'edges', None) or []
    if not nodes:
        return None

    nodes_by_id = {n.get('id'): n for n in nodes if n.get('id')}
    best_node = None
    best_score = 0
    for node in nodes:
        score = _node_financial_score(node, nodes_by_id, edges)
        if score > best_score:
            best_score = score
            best_node = node

    return best_node if best_score >= 5 else None
