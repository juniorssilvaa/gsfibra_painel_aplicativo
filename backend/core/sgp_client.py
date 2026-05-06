import requests
import logging
import re


def _mascarar_cpf_cnpj(val):
    """Mascara CPF/CNPJ para log: mostra só últimos 4 dígitos."""
    if not val:
        return "***"
    s = str(val).replace(".", "").replace("-", "").replace("/", "")
    if len(s) >= 4:
        return "***" + s[-4:]
    return "***"

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
            self.logger.debug("[SGP] listar_clientes | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(r.json() if r.text else None))
            return r.json()
        except Exception as e:
            self.logger.debug("[SGP] listar_clientes | erro=%s", e)
            raise

    def consultar_cliente(self, cpf):
        cpf_limpo = str(cpf).replace(".", "").replace("-", "").replace("/", "")
        self.logger.info("[SGP] consultar_cliente | POST %s/api/ura/consultacliente/ | cpfcnpj=%s", self.base_url, _mascarar_cpf_cnpj(cpf))
        try:
            data = {
                'token': self.token,
                'app': self.app_name,
                'cpfcnpj': cpf_limpo
            }
            r = requests.post(
                f'{self.base_url}/api/ura/consultacliente/',
                data=data,
                timeout=30
            )
            resp = r.json() if r.text else {}
            n_contratos = len(resp.get("contratos", []))
            # Diagnóstico: ver se o SGP retorna nome do titular no nível da resposta (evita usar nome do contrato)
            top_keys = list(resp.keys()) if isinstance(resp, dict) else []
            tem_nome_topo = any(k for k in ('razaoSocial', 'nome', 'nomeCliente', 'cliente') if resp.get(k))
            
            # Log detalhado: nome no topo e primeiro contrato (mascarado parcialmente)
            nome_topo = (resp.get('razaoSocial') or resp.get('nome') or resp.get('nomeCliente') or '')
            nome_topo_mascarado = nome_topo[:3] + "***" + nome_topo[-2:] if len(nome_topo) > 5 else "***" if nome_topo else "vazio"
            primeiro_contrato_nome = resp.get("contratos", [{}])[0].get('razaoSocial', '') if resp.get("contratos") else ''
            primeiro_contrato_nome_mascarado = primeiro_contrato_nome[:3] + "***" + primeiro_contrato_nome[-2:] if len(primeiro_contrato_nome) > 5 else "***" if primeiro_contrato_nome else "vazio"
            
            # Log completo da resposta do SGP (mascarado) para diagnóstico de nomes errados
            resp_str = str(resp)
            # Mascarar CPFs/CNPJs na resposta
            resp_str_mascarado = re.sub(r'(\d{3})\d{6}(\d{2})', r'\1***\2', resp_str)
            resp_str_mascarado = re.sub(r'(\d{2})\d{7}(\d{2})', r'\1***\2', resp_str_mascarado)  # CNPJ
            
            self.logger.warning(
                "[SGP] consultar_cliente | HTTP %s | CPF=%s | contratos=%s | keys=%s | nome_topo=%s | primeiro_contrato_nome=%s | resposta_mascarada=%s",
                r.status_code,
                cpf_limpo[:3] + "***" + cpf_limpo[-2:] if len(cpf_limpo) >= 5 else "***",
                n_contratos,
                top_keys,
                nome_topo_mascarado,
                primeiro_contrato_nome_mascarado,
                resp_str_mascarado[:500] if len(resp_str_mascarado) > 500 else resp_str_mascarado,  # Limitar tamanho do log
            )
            return resp
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
            resp = r.json() if r.text else {}
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
            self.logger.debug("[SGP] listar_contratos | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(r.json() if r.text else None))
            return r.json()
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
            resp = r.json() if r.text else {}
            self.logger.info("[SGP] liberar_por_confianca | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.warning("[SGP] liberar_por_confianca | erro=%s", e)
            raise

    # ==========================================================
    # CHAMADO TÉCNICO (CORRIGIDO DEFINITIVO)
    # ==========================================================
    def criar_chamado(self, contrato, conteudo, ocorrenciatipo):
        """
        Criar chamado técnico no SGP via API URA

        ocorrenciatipo: código do tipo de ocorrência no SGP (obrigatório, definido pelo provedor).

        Endpoint:
            POST /api/ura/chamado/

        Regras IMPORTANTES:
        - NÃO enviar Authorization header
        - NÃO enviar App header
        - NÃO enviar Content-Type manualmente
        - Enviar TUDO via form-data (data=)
        """
        if ocorrenciatipo is None or (isinstance(ocorrenciatipo, str) and not str(ocorrenciatipo).strip()):
            return {
                "success": False,
                "error": "ocorrenciatipo é obrigatório (código do tipo de ocorrência no SGP).",
            }
        try:
            o_int = int(str(ocorrenciatipo).strip())
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": "ocorrenciatipo inválido: use um número inteiro.",
            }
        if o_int < 1:
            return {
                "success": False,
                "error": "ocorrenciatipo inválido.",
            }
        ocorrenciatipo = o_int

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
            resp = r.json() if r.text else {}
            self.logger.warning("[SGP][DEBUG] Resposta Bruta do SGP: %s", resp)
            self.logger.info("[SGP] listar_faturas_v2 | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(resp))
            return resp
        except Exception as e:
            self.logger.warning("[SGP] listar_faturas_v2 | erro=%s", e)
            return {}

    def segunda_via_fatura(self, cpf_cnpj):
        """Metodo legado para compatibilidade. Usa listar_faturas_v2."""
        return self.listar_faturas_v2(cpf_cnpj=cpf_cnpj)

    def gerar_pix(self, fatura):
        self.logger.debug("[SGP] gerar_pix | GET %s/api/ura/pagamento/pix/%s", self.base_url, fatura)
        try:
            r = requests.get(
                f'{self.base_url}/api/ura/pagamento/pix/{fatura}',
                headers=self._headers(),
                timeout=30
            )
            self.logger.debug("[SGP] gerar_pix | HTTP %s | resumo=%s", r.status_code, _resumo_resposta(r.json() if r.text else None))
            return r.json()
        except Exception as e:
            self.logger.debug("[SGP] gerar_pix | erro=%s", e)
            raise

    def listar_titulos(self, cpf_cnpj=None, contrato=None, limit=250):
        """Metodo legado para compatibilidade. Usa listar_faturas_v2."""
        return self.listar_faturas_v2(contrato_id=contrato, cpf_cnpj=cpf_cnpj)

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
            resp = r.json() if r.text else {}
            n_manut = len(resp) if isinstance(resp, list) else len(resp.get("manutencoes", [])) if isinstance(resp, dict) else 0
            self.logger.info("[SGP] listar_manutencoes | HTTP %s | n_manutencoes=%s", r.status_code, n_manut)
            return resp
        except Exception as e:
            self.logger.warning("[SGP] listar_manutencoes | erro=%s", e)
            raise
