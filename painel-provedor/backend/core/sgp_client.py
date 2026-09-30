import json
import requests
import logging
import re


class SGPInvalidResponse(Exception):
    """Resposta HTTP do SGP vazia, HTML ou não-JSON."""

    def __init__(self, message, status_code=None, body_preview=None):
        super().__init__(message)
        self.status_code = status_code
        self.body_preview = body_preview


def _mascarar_cpf_cnpj(val):
    """Mascara CPF/CNPJ para log: mostra só últimos 4 dígitos."""
    if not val:
        return "***"
    s = str(val).replace(".", "").replace("-", "").replace("/", "")
    if len(s) >= 4:
        return "***" + s[-4:]
    return "***"


def _preview_corpo(text, max_len=200):
    """Preview do corpo HTTP mascarando CPF/CNPJ."""
    if not text:
        return ""
    preview = re.sub(r"\s+", " ", str(text)).strip()[:max_len]
    preview = re.sub(r"(\d{3})\d{6}(\d{2})", r"\1***\2", preview)
    preview = re.sub(r"(\d{2})\d{7}(\d{2})", r"\1***\2", preview)
    return preview


def _parse_json_response(response, logger=None, context="SGP"):
    """
    Parse seguro do corpo HTTP do SGP.
    Evita JSONDecodeError em corpo vazio, whitespace ou HTML.
    """
    status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", None) or {}
    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    raw = getattr(response, "text", None) or ""
    text = raw.strip()

    if not text:
        msg = (
            f"SGP retornou resposta vazia (HTTP {status}). "
            "Verifique URL, token e app da integração."
        )
        if logger:
            logger.warning("[%s] %s | content-type=%s", context, msg, content_type)
        raise SGPInvalidResponse(msg, status_code=status, body_preview="")

    try:
        return json.loads(text)
    except ValueError as e:
        preview = _preview_corpo(text)
        msg = (
            f"SGP retornou resposta inválida (HTTP {status}, não-JSON). "
            "Verifique URL, token e app da integração."
        )
        if logger:
            logger.warning(
                "[%s] parse JSON falhou | HTTP %s | content-type=%s | preview=%s | erro=%s",
                context,
                status,
                content_type,
                preview,
                e,
            )
        raise SGPInvalidResponse(msg, status_code=status, body_preview=preview) from e


def _resumo_resposta(resp, max_len=200):
    """Resumo seguro da resposta para log (evita PII)."""
    if resp is None:
        return "None"
    if isinstance(resp, dict):
        keys = list(resp.keys())[:8]
        status = resp.get("status", resp.get("success", ""))
        n_contratos = len(resp.get("contratos", []))
        if "contratos" in resp:
            return f"dict(keys={keys}, status={status}, contratos={n_contratos})"
        return f"dict(keys={keys}, status={status})"
    s = str(resp)[:max_len]
    return s + "..." if len(str(resp)) > max_len else s


OCORRENCIA_STATUS = {0: "Aberta", 1: "Encerrada", 2: "Em execução", 3: "Pendente"}

_CHAVES_LISTA_CHAMADOS = (
    "chamados", "ocorrencias", "ocorrencia", "result", "results",
    "data", "dados", "lista", "items", "registros",
)


def _extrair_lista_chamados(resp):
    """Lista de ocorrências na resposta do SGP; None se o formato não for reconhecido."""
    if isinstance(resp, list):
        return [i for i in resp if isinstance(i, dict)]
    if not isinstance(resp, dict):
        return None
    for key in _CHAVES_LISTA_CHAMADOS:
        val = resp.get(key)
        if isinstance(val, list):
            return [i for i in val if isinstance(i, dict)]
        if isinstance(val, dict):
            for sub in _CHAVES_LISTA_CHAMADOS:
                if isinstance(val.get(sub), list):
                    return [i for i in val[sub] if isinstance(i, dict)]
    if resp.get("status") in (1, "1", True) or resp.get("success") is True:
        return []
    return None


def _primeiro_valor(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _codigo_status_ocorrencia(raw):
    if isinstance(raw, dict):
        raw = _primeiro_valor(raw, "id", "codigo", "status") or raw.get("descricao")
    if raw is None:
        return None
    txt = str(raw).strip().lower()
    if txt.lstrip("-").isdigit():
        return int(txt)
    if "abert" in txt:
        return 0
    if "encerr" in txt or "fechad" in txt or "finaliz" in txt:
        return 1
    if "execu" in txt:
        return 2
    if "pend" in txt:
        return 3
    return None


def _formatar_data_sgp(valor):
    """'2026-09-30T08:00:00' -> '30/09/2026 08:00'; outros formatos passam como vieram."""
    if not valor:
        return None
    txt = str(valor).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", txt)
    if not m:
        return txt
    ano, mes, dia, hora, minuto = m.groups()
    data = f"{dia}/{mes}/{ano}"
    return f"{data} {hora}:{minuto}" if hora else data


def _normalizar_chamado(item):
    """Formato único de ocorrência: status numérico (0-3), protocolo, tipo e datas."""
    if not isinstance(item, dict):
        return None
    base = dict(item)
    if isinstance(item.get("ocorrencia"), dict):
        base.update(item["ocorrencia"])
    status = _codigo_status_ocorrencia(_primeiro_valor(
        base, "oc_status", "ocorrencia_status", "status_ocorrencia", "statusOcorrencia", "status",
    ))
    tipo = _primeiro_valor(
        base, "oc_tipo_descricao", "tipo_descricao", "ocorrenciatipo_descricao",
        "tipo", "ocorrenciatipo", "oc_tipo", "assunto",
    )
    if isinstance(tipo, dict):
        tipo = _primeiro_valor(tipo, "descricao", "nome")
    conteudo = _primeiro_valor(base, "oc_conteudo", "conteudo", "descricao", "observacao")
    return {
        "id": _primeiro_valor(base, "oc_id", "id", "ocorrencia_id", "codigo"),
        "protocolo": _primeiro_valor(base, "oc_protocolo", "protocolo", "numero_protocolo", "numero"),
        "status": status,
        "status_descricao": OCORRENCIA_STATUS.get(status),
        "tipo": str(tipo).strip() if tipo else None,
        "data_cadastro": _formatar_data_sgp(_primeiro_valor(
            base, "oc_data_cadastro", "data_cadastro", "dataCadastro", "data_abertura", "abertura", "data",
        )),
        "data_agendamento": _formatar_data_sgp(_primeiro_valor(
            base, "os_data_agendamento", "data_agendamento", "dataAgendamento", "agendamento",
        )),
        "conteudo": str(conteudo).strip()[:200] if conteudo else None,
    }


class SGPClient:
    def __init__(self, base_url, token, app_name):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.app_name = app_name
        self.logger = logging.getLogger(__name__)

    # ==========================================================
    # HEADERS PADRÃO (APENAS PARA ENDPOINTS QUE ACEITAM HEADER)
    # ==========================================================
    def _headers(self, include_content_type=True):
        headers = {}
        if include_content_type:
            headers['Content-Type'] = 'application/json'
        return headers

    # ==========================================================
    # CLIENTES
    # ==========================================================
    def listar_clientes(self):
        self.logger.debug("[SGP] listar_clientes | GET %s/api/ura/clientes/", self.base_url)
        try:
            r = requests.get(
                f'{self.base_url}/api/ura/clientes/',
                headers=self._headers(),
                timeout=30
            )
            resp = _parse_json_response(r, logger=self.logger, context="SGP listar_clientes")
            self.logger.debug("[SGP] listar_clientes | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.debug("[SGP] listar_clientes | erro=%s", e)
            raise

    def consultar_cliente(self, cpf):
        cpf_limpo = re.sub(r"\D", "", str(cpf or ""))
        self.logger.info(
            "[SGP] consultar_cliente | POST %s/api/ura/consultacliente/ | cpfcnpj=%s",
            self.base_url,
            _mascarar_cpf_cnpj(cpf_limpo),
        )
        if len(cpf_limpo) not in (11, 14):
            raise ValueError("CPF/CNPJ inválido. Informe 11 ou 14 dígitos.")

        try:
            data = {
                'token': self.token,
                'app': self.app_name,
                'cpfcnpj': cpf_limpo,
            }
            r = requests.post(
                f'{self.base_url}/api/ura/consultacliente/',
                data=data,
                timeout=30,
            )
            if r.status_code >= 400:
                preview = _preview_corpo(r.text)
                msg = (
                    f"SGP recusou a consulta (HTTP {r.status_code}). "
                    "Verifique URL, token e app da integração."
                )
                self.logger.warning(
                    "[SGP] consultar_cliente | HTTP %s | preview=%s",
                    r.status_code,
                    preview,
                )
                raise SGPInvalidResponse(msg, status_code=r.status_code, body_preview=preview)

            resp = _parse_json_response(r, logger=self.logger, context="SGP consultar_cliente")
            if not isinstance(resp, dict):
                raise SGPInvalidResponse(
                    "SGP retornou formato inesperado na consulta de cliente.",
                    status_code=r.status_code,
                    body_preview=_preview_corpo(str(resp)),
                )

            n_contratos = len(resp.get("contratos", []) or [])
            top_keys = list(resp.keys())
            nome_topo = (resp.get('razaoSocial') or resp.get('nome') or resp.get('nomeCliente') or '')
            nome_topo_mascarado = (
                nome_topo[:3] + "***" + nome_topo[-2:]
                if len(nome_topo) > 5
                else ("***" if nome_topo else "vazio")
            )
            contratos = resp.get("contratos") or []
            primeiro_contrato_nome = contratos[0].get('razaoSocial', '') if contratos and isinstance(contratos[0], dict) else ''
            primeiro_contrato_nome_mascarado = (
                primeiro_contrato_nome[:3] + "***" + primeiro_contrato_nome[-2:]
                if len(primeiro_contrato_nome) > 5
                else ("***" if primeiro_contrato_nome else "vazio")
            )

            resp_str_mascarado = _preview_corpo(str(resp), max_len=500)

            self.logger.warning(
                "[SGP] consultar_cliente | HTTP %s | CPF=%s | contratos=%s | keys=%s | nome_topo=%s | primeiro_contrato_nome=%s | resposta_mascarada=%s",
                r.status_code,
                cpf_limpo[:3] + "***" + cpf_limpo[-2:] if len(cpf_limpo) >= 5 else "***",
                n_contratos,
                top_keys,
                nome_topo_mascarado,
                primeiro_contrato_nome_mascarado,
                resp_str_mascarado,
            )
            return resp
        except SGPInvalidResponse:
            raise
        except ValueError:
            raise
        except Exception as e:
            self.logger.warning("[SGP] consultar_cliente | erro=%s", e)
            raise

    # ==========================================================
    # ACESSO / CONTRATO
    # ==========================================================
    def verifica_acesso(self, contrato):
        self.logger.info("[SGP] verifica_acesso | POST %s/api/ura/verificaacesso/ | contrato=%s", self.base_url, contrato)
        try:
            data = {
                'token': self.token,
                'app': self.app_name,
                'contrato': str(contrato)
            }
            r = requests.post(
                f'{self.base_url}/api/ura/verificaacesso/',
                data=data,
                timeout=30
            )
            resp = _parse_json_response(r, logger=self.logger, context="SGP verifica_acesso")
            if not isinstance(resp, dict):
                resp = {}
            status = resp.get("status", resp.get("status_conexao", ""))
            self.logger.info("[SGP] verifica_acesso | HTTP %s | status=%s", r.status_code, status)
            return resp
        except Exception as e:
            self.logger.warning("[SGP] verifica_acesso | erro=%s", e)
            raise

    def listar_contratos(self, cliente_id):
        self.logger.debug("[SGP] listar_contratos | POST %s/api/ura/listacontrato/ | cliente_id=%s", self.base_url, cliente_id)
        try:
            r = requests.post(
                f'{self.base_url}/api/ura/listacontrato/',
                json={'cliente_id': cliente_id},
                headers=self._headers(),
                timeout=30
            )
            resp = _parse_json_response(r, logger=self.logger, context="SGP listar_contratos")
            self.logger.debug("[SGP] listar_contratos | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.debug("[SGP] listar_contratos | erro=%s", e)
            raise

    # ==========================================================
    # LIBERAÇÃO POR CONFIANÇA
    # ==========================================================
    def liberar_por_confianca(self, contrato, cpf_cnpj=None, conteudo=None):
        self.logger.info(
            "[SGP] liberar_por_confianca | POST %s/api/ura/liberacaopromessa/ | contrato=%s cpfcnpj=%s",
            self.base_url, contrato, _mascarar_cpf_cnpj(cpf_cnpj)
        )
        data = {
            'token': self.token,
            'app': self.app_name,
            'contrato': str(contrato),
            'conteudolimpo': 1
        }

        if cpf_cnpj:
            cpf_cnpj_limpo = (
                str(cpf_cnpj)
                .replace('.', '')
                .replace('-', '')
                .replace('/', '')
            )
            data['cpfCnpj'] = cpf_cnpj_limpo

        if conteudo:
            data['conteudo'] = str(conteudo).strip()
        else:
            data['conteudo'] = "Liberação Via NioChat"

        try:
            r = requests.post(
                f'{self.base_url}/api/ura/liberacaopromessa/',
                data=data,
                timeout=30
            )
            resp = _parse_json_response(r, logger=self.logger, context="SGP liberar_por_confianca")
            if not isinstance(resp, dict):
                resp = {}
            self.logger.info("[SGP] liberar_por_confianca | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.warning("[SGP] liberar_por_confianca | erro=%s", e)
            raise

    # ==========================================================
    # CHAMADO TÉCNICO (CORRIGIDO DEFINITIVO)
    # ==========================================================
    def criar_chamado(self, contrato, conteudo, ocorrenciatipo=1):
        """
        Criar chamado técnico no SGP via API URA

        Endpoint:
            POST /api/ura/chamado/

        Regras IMPORTANTES:
        - NÃO enviar Authorization header
        - NÃO enviar App header
        - NÃO enviar Content-Type manualmente
        - Enviar TUDO via form-data (data=)
        """

        url = f'{self.base_url}/api/ura/chamado/'

        data = {
            'token': self.token,
            'app': self.app_name,
            'contrato': str(contrato),
            'conteudo': conteudo,
            'ocorrenciatipo': str(ocorrenciatipo),
            'conteudolimpo': 1
        }

        self.logger.info(
            f"[SGP] Criando chamado | Contrato={contrato} | Tipo={ocorrenciatipo}"
        )
        self.logger.info(
            f"[SGP] Payload completo: {data}"
        )

        try:
            response = requests.post(
                url,
                data=data,
                timeout=10
            )

            self.logger.info(
                f"[SGP] HTTP {response.status_code} | Response: {response.text}"
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Erro HTTP {response.status_code}",
                    "raw": response.text
                }

            try:
                res_json = response.json()
            except ValueError:
                return {
                    "success": False,
                    "error": "Resposta inválida do SGP",
                    "raw": response.text
                }

            if res_json.get("status") == 1:
                return {
                    "success": True,
                    "protocolo": res_json.get("protocolo"),
                    "chamado_id": res_json.get("id"),
                    "raw": res_json
                }

            return {
                "success": False,
                "error": res_json.get("msg") or "Falha ao criar chamado no SGP",
                "raw": res_json
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Timeout na comunicação com o SGP"
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "error": f"Erro de conexão com o SGP: {str(e)}"
            }
        except Exception as e:
            self.logger.exception("[SGP] Erro inesperado ao criar chamado")
            return {
                "success": False,
                "error": str(e)
            }

    def listar_tipos_ocorrencia(self, cpf_cnpj=None, senha=None):
        """
        Lista tipos de ocorrência do SGP (POST /api/central/tipoocorrencia/list/).
        Envia token/app e, quando disponíveis, cpfcnpj + senha da central do assinante;
        se o SGP recusar essa combinação, repete só com token/app.
        Retorna [{'codigo': int, 'descricao': str}, ...].
        """
        url = f'{self.base_url}/api/central/tipoocorrencia/list/'
        base_data = {'token': self.token, 'app': self.app_name}
        tentativas = []
        cpf_limpo = re.sub(r"\D", "", str(cpf_cnpj or ""))
        if cpf_limpo and senha:
            tentativas.append({**base_data, 'cpfcnpj': cpf_limpo, 'senha': str(senha)})
        tentativas.append(base_data)

        ultimo_erro = None
        for data in tentativas:
            try:
                r = requests.post(url, data=data, timeout=20)
                self.logger.info(
                    "[SGP] listar_tipos_ocorrencia | HTTP %s | cpfcnpj=%s",
                    r.status_code, _mascarar_cpf_cnpj(data.get('cpfcnpj')),
                )
                if r.status_code != 200:
                    ultimo_erro = f"HTTP {r.status_code}"
                    continue
                resp = _parse_json_response(r, logger=self.logger, context="SGP listar_tipos_ocorrencia")
                itens = resp if isinstance(resp, list) else (
                    resp.get('tipos') or resp.get('result') or resp.get('data') or []
                    if isinstance(resp, dict) else []
                )
                tipos = []
                for it in itens:
                    if not isinstance(it, dict):
                        continue
                    codigo = it.get('codigo', it.get('id'))
                    descricao = (it.get('descricao') or it.get('nome') or '').strip()
                    if codigo is not None and descricao:
                        tipos.append({'codigo': codigo, 'descricao': descricao})
                if tipos:
                    return sorted(tipos, key=lambda t: t['descricao'].lower())
                ultimo_erro = "lista vazia"
            except Exception as e:
                ultimo_erro = str(e)
                self.logger.warning("[SGP] listar_tipos_ocorrencia | erro=%s", e)
        raise SGPInvalidResponse(f"Não foi possível listar os tipos de ocorrência ({ultimo_erro}).")

    def listar_chamados(self, contrato=None, cpf_cnpj=None, senha=None, cliente=None):
        """
        Lista ocorrências/OS do contrato (POST /api/central/chamado/list/).
        Autentica com cpfcnpj + senha da central; envia token/app também.
        Status da ocorrência: 0 Aberta, 1 Encerrada, 2 Em execução, 3 Pendente.
        Retorna {'success': True, 'chamados': [...]} ou {'success': False, 'error': str}.
        """
        url = f'{self.base_url}/api/central/chamado/list/'
        payload = {'token': self.token, 'app': self.app_name}
        cpf_limpo = re.sub(r"\D", "", str(cpf_cnpj or ""))
        if cpf_limpo and senha:
            payload['cpfcnpj'] = cpf_limpo
            payload['senha'] = str(senha)
        contrato_limpo = re.sub(r"\D", "", str(contrato or ""))
        cliente_limpo = re.sub(r"\D", "", str(cliente or ""))
        if contrato_limpo:
            payload['contrato'] = int(contrato_limpo)
        elif cliente_limpo:
            payload['cliente'] = int(cliente_limpo)
        elif 'cpfcnpj' not in payload:
            return {'success': False, 'error': 'Informe contrato, cliente ou CPF/CNPJ com senha.'}

        ultimo_erro = None
        for modo in ('json', 'form'):
            try:
                if modo == 'json':
                    r = requests.post(url, json=payload, timeout=20)
                else:
                    r = requests.post(url, data=payload, timeout=20)
                self.logger.info(
                    "[SGP] listar_chamados | %s | HTTP %s | contrato=%s | com_senha=%s",
                    modo, r.status_code, contrato_limpo or None, bool(payload.get('senha')),
                )
                if r.status_code != 200:
                    ultimo_erro = f"HTTP {r.status_code}"
                    continue
                resp = _parse_json_response(r, logger=self.logger, context="SGP listar_chamados")
                itens = _extrair_lista_chamados(resp)
                if itens is None:
                    msg = None
                    if isinstance(resp, dict):
                        msg = resp.get('msg') or resp.get('mensagem') or resp.get('erro') or resp.get('error')
                    ultimo_erro = str(msg or 'resposta sem lista de chamados')
                    self.logger.warning(
                        "[SGP] listar_chamados | sem lista | chaves=%s | msg=%s",
                        list(resp.keys())[:12] if isinstance(resp, dict) else type(resp).__name__,
                        ultimo_erro,
                    )
                    continue
                chamados = [c for c in (_normalizar_chamado(it) for it in itens) if c]
                self.logger.info(
                    "[SGP] listar_chamados | total=%s | por_status=%s | campos_item=%s",
                    len(chamados),
                    {s: sum(1 for c in chamados if c.get('status') == s) for s in (0, 1, 2, 3, None)},
                    sorted(itens[0].keys())[:25] if itens and isinstance(itens[0], dict) else [],
                )
                return {'success': True, 'chamados': chamados}
            except Exception as e:
                ultimo_erro = str(e)
                self.logger.warning("[SGP] listar_chamados | %s | erro=%s", modo, e)
        return {'success': False, 'error': ultimo_erro or 'Falha ao listar chamados no SGP'}

    # ==========================================================
    # FATURA / PAGAMENTOS
    # ==========================================================
    def listar_faturas_v2(self, contrato_id=None, cpf_cnpj=None):
        """
        Lista faturas detalhadas via endpoint /api/ura/fatura2via/
        Suporta busca por Contrato, CPF/CNPJ ou ambos.
        """
        self.logger.info("[SGP] listar_faturas_v2 | POST %s/api/ura/fatura2via/ | contrato=%s cpfcnpj=%s", 
                          self.base_url, contrato_id, _mascarar_cpf_cnpj(cpf_cnpj))
        try:
            data = {
                'token': self.token,
                'app': self.app_name,
            }
            if contrato_id:
                data['contrato'] = str(contrato_id)
            if cpf_cnpj:
                data['cpfcnpj'] = str(cpf_cnpj)
            
            self.logger.warning("[SGP][DEBUG] Enviando POST para /api/ura/fatura2via/ | Payload: %s", data)
                
            r = requests.post(
                f'{self.base_url}/api/ura/fatura2via/',
                data=data,
                timeout=30,
                verify=False # Conforme script de referência
            )
            try:
                resp = _parse_json_response(r, logger=self.logger, context="SGP listar_faturas_v2")
            except SGPInvalidResponse as e:
                self.logger.warning("[SGP] listar_faturas_v2 | %s", e)
                return {}
            if not isinstance(resp, dict):
                resp = {}
            self.logger.warning("[SGP][DEBUG] Resposta Bruta do SGP: %s", _resumo_resposta(resp))
            self.logger.info("[SGP] listar_faturas_v2 | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.warning("[SGP] listar_faturas_v2 | erro=%s", e)
            return {}

    def segunda_via_fatura(self, cpf_cnpj):
        """Metodo legado para compatibilidade. Usa listar_faturas_v2."""
        return self.listar_faturas_v2(cpf_cnpj=cpf_cnpj)

    def gerar_pix(self, fatura):
        """
        Gera/obtém código PIX (copia e cola) para uma fatura via URA.
        Tenta POST com fatura no path e depois GET com token na query.
        """
        fatura_id = str(fatura).strip()
        data = {
            'token': self.token,
            'app': self.app_name,
            'fatura': fatura_id,
        }
        urls = [
            ('POST', f'{self.base_url}/api/ura/pagamento/pix/{fatura_id}/', data, None),
            ('POST', f'{self.base_url}/api/ura/pagamento/pix/', data, None),
            (
                'GET',
                f'{self.base_url}/api/ura/pagamento/pix/{fatura_id}/',
                None,
                {'token': self.token, 'app': self.app_name},
            ),
        ]
        last_resp = {}
        try:
            for method, url, body, params in urls:
                self.logger.info("[SGP] gerar_pix | %s %s | fatura=%s", method, url, fatura_id)
                if method == 'POST':
                    r = requests.post(url, data=body, timeout=30)
                else:
                    r = requests.get(url, params=params, timeout=30)
                try:
                    resp = _parse_json_response(r, logger=self.logger, context="SGP gerar_pix")
                except SGPInvalidResponse:
                    resp = {}
                last_resp = resp if isinstance(resp, dict) else {'raw': resp}
                self.logger.info(
                    "[SGP] gerar_pix | HTTP %s | resumo=%s",
                    r.status_code,
                    _resumo_resposta(resp),
                )
                if r.status_code == 200 and isinstance(resp, dict):
                    # sucesso útil se tiver algum campo de PIX ou status ok
                    if any(
                        resp.get(k)
                        for k in (
                            'codigopix',
                            'codigo_pix',
                            'pix',
                            'pix_copia_cola',
                            'emv',
                            'qrcode',
                        )
                    ) or resp.get('status') in (1, '1', True):
                        return resp
                if r.status_code not in (404, 405, 401, 403):
                    # outro erro: devolve para o caller decidir
                    return last_resp
            return last_resp
        except Exception as e:
            self.logger.warning("[SGP] gerar_pix | erro=%s", e)
            raise

    def listar_titulos(self, cpf_cnpj=None, contrato=None, limit=250):
        """Metodo legado para compatibilidade. Usa listar_faturas_v2."""
        return self.listar_faturas_v2(contrato_id=contrato, cpf_cnpj=cpf_cnpj)

    # ==========================================================
    # VIABILIDADE
    # ==========================================================
    def consultar_viabilidade(
        self,
        *,
        logradouro=None,
        numero_inicial=None,
        numero_final=None,
        bairro=None,
        cep=None,
        cidade=None,
    ):
        """
        Consulta viabilidade técnica de instalação.

        Endpoint:
            POST /api/ura/viabilidade/

        Auth e filtros via form-data (token + app + ao menos um filtro de endereço).
        """
        data = {
            'token': self.token,
            'app': self.app_name,
        }
        if logradouro:
            data['logradouro'] = str(logradouro).strip()
        if numero_inicial is not None and str(numero_inicial).strip() != '':
            data['numero_inicial'] = str(numero_inicial).strip()
        if numero_final is not None and str(numero_final).strip() != '':
            data['numero_final'] = str(numero_final).strip()
        if bairro:
            data['bairro'] = str(bairro).strip()
        if cep:
            cep_digits = re.sub(r'\D', '', str(cep))
            if len(cep_digits) == 8:
                data['cep'] = f"{cep_digits[:5]}-{cep_digits[5:]}"
            elif str(cep).strip():
                data['cep'] = str(cep).strip()
        if cidade:
            data['cidade'] = str(cidade).strip()

        self.logger.info(
            "[SGP] consultar_viabilidade | POST %s/api/ura/viabilidade/ | cidade=%s bairro=%s logradouro=%s cep=%s num=%s-%s",
            self.base_url,
            data.get('cidade', ''),
            data.get('bairro', ''),
            data.get('logradouro', ''),
            data.get('cep', ''),
            data.get('numero_inicial', ''),
            data.get('numero_final', ''),
        )
        try:
            r = requests.post(
                f'{self.base_url}/api/ura/viabilidade/',
                data=data,
                timeout=30,
            )
            try:
                resp = _parse_json_response(r, logger=self.logger, context="SGP consultar_viabilidade")
            except SGPInvalidResponse as e:
                if r.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Erro HTTP {r.status_code}",
                        "raw": _preview_corpo(r.text),
                    }
                raise
            self.logger.info(
                "[SGP] consultar_viabilidade | HTTP %s | resumo=%s",
                r.status_code,
                _resumo_resposta(resp),
            )
            if r.status_code != 200:
                return {
                    "success": False,
                    "error": f"Erro HTTP {r.status_code}",
                    "raw": resp if resp else _preview_corpo(r.text),
                }
            if isinstance(resp, dict):
                return resp
            if isinstance(resp, list):
                return {"status": 1, "results": resp}
            return {"status": 1, "raw": resp}
        except Exception as e:
            self.logger.warning("[SGP] consultar_viabilidade | erro=%s", e)
            raise

    def consultar_viabilidade_instalacao(self, *, gateway, raio, latitude, longitude):
        """
        Consulta viabilidade por coordenadas no mapa (CTO próximas).

        Endpoint:
            GET /api/ura/viabilidadeinstalacao/

        Params:
            token, app, gateway, raio, coordenada (\"lat,lng\")
        """
        try:
            gateway_id = int(gateway)
            raio_m = int(raio)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": "gateway e raio devem ser numeros inteiros.",
            }

        lat = str(latitude).strip().replace(',', '.')
        lng = str(longitude).strip().replace(',', '.')
        if not lat or not lng:
            return {
                "success": False,
                "error": "latitude e longitude sao obrigatorias.",
            }

        coordenada = f"{lat},{lng}"
        params = {
            'token': self.token,
            'app': self.app_name,
            'gateway': gateway_id,
            'raio': raio_m,
            'coordenada': coordenada,
        }
        url = f'{self.base_url}/api/ura/viabilidadeinstalacao/'
        self.logger.info(
            "[SGP] consultar_viabilidade_instalacao | GET %s | gateway=%s raio=%s coordenada=%s",
            url, gateway_id, raio_m, coordenada,
        )
        try:
            r = requests.get(url, params=params, timeout=30)
            try:
                resp = _parse_json_response(r, logger=self.logger, context="SGP consultar_viabilidade_instalacao")
            except SGPInvalidResponse:
                resp = {}
            self.logger.info(
                "[SGP] consultar_viabilidade_instalacao | HTTP %s | resumo=%s",
                r.status_code,
                _resumo_resposta(resp),
            )
            if r.status_code != 200:
                msg = resp.get('msg') if isinstance(resp, dict) else None
                return {
                    "success": False,
                    "error": msg or f"Erro HTTP {r.status_code}",
                    "raw": resp if resp else _preview_corpo(r.text),
                }
            return {
                "success": True,
                "raw": resp,
            }
        except Exception as e:
            self.logger.warning("[SGP] consultar_viabilidade_instalacao | erro=%s", e)
            raise

    # ==========================================================
    # MANUTENÇÕES
    # ==========================================================
    def listar_manutencoes(self, cpf):
        self.logger.info("[SGP] listar_manutencoes | POST %s/api/ura/manutencao/list/ | cpf=%s", self.base_url, _mascarar_cpf_cnpj(cpf))
        try:
            r = requests.post(
                f'{self.base_url}/api/ura/manutencao/list/',
                json={'cpf': cpf},
                headers=self._headers(),
                timeout=30
            )
            resp = _parse_json_response(r, logger=self.logger, context="SGP listar_manutencoes")
            n_manut = len(resp) if isinstance(resp, list) else len(resp.get("manutencoes", [])) if isinstance(resp, dict) else 0
            self.logger.info("[SGP] listar_manutencoes | HTTP %s | n_manutencoes=%s", r.status_code, n_manut)
            return resp
        except Exception as e:
            self.logger.warning("[SGP] listar_manutencoes | erro=%s", e)
            raise
