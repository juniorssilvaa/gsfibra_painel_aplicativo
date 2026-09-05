import json
import logging
import os
import re
import secrets
import requests
from django.conf import settings
from ..models import SystemConfig, User

logger = logging.getLogger(__name__)

class PortainerService:
    def __init__(self, vps):
        self.vps = vps
        self.api_url = self.vps.api_url.rstrip('/')
        self.token = self.vps.portainer_api_key
        self.endpoint_id = self.vps.endpoint_id
        self.headers = {
            "X-API-Key": self.token,
            "Content-Type": "application/json"
        }

    def _prepare_compose(self, subdomain, provedor=None, stack_name=None, image_tag=None):
        """
        Lê o docker-compose do painel do provedor e prepara para o deploy do cliente.
        Substitui __TRAEFIK_ROUTER_PREFIX__ e __PROVIDER_HOST__ (Swarm + Traefik).
        """
        try:
            # Template: niohub/painel-provedor/docker-compose.yml (BASE_DIR = superadmin/backend/)
            base_dir = str(settings.BASE_DIR)
            root_dir = os.path.dirname(os.path.dirname(base_dir))
            compose_path = os.path.join(root_dir, 'painel-provedor', 'docker-compose.yml')
            
            logger.info(f"Lendo template de: {compose_path}")
            
            with open(compose_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. Remover container_name para evitar conflitos se houver + de 1 provedor na mesma VPS
            # O Portainer vai usar o nome da Stack como prefixo automaticamente.
            content = re.sub(r'^\s*container_name:.*$', '', content, flags=re.MULTILINE)
            # No Swarm, aliases em redes externas podem causar erros de deploy/rejeição.
            content = re.sub(r'^\s*aliases:.*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'^\s*-\s*niochat_postgres.*$', '', content, flags=re.MULTILINE)
            # Em multi-tenant, não podemos expor a porta 5432 no host para cada stack (conflito).
            # Removemos a seção de portas do postgres.
            content = re.sub(r'^\s*ports:.*?\n\s*-\s*"5432:5432".*?\n', '\n', content, flags=re.DOTALL | re.MULTILINE)

            # 2. Substituir domínios fixos pelo subdomínio do cliente
            # Alvo: Host(`api.niohub.com.br`) || Host(`chat.niohub.com.br`)
            content = content.replace('api.niohub.com.br', subdomain)
            content = content.replace('chat.niohub.com.br', subdomain)
            
            # 3. Normalizar referências à rede interna (nethub)
            content = re.sub(r'(?i)NioNet', 'nethub', content)
            content = content.replace('nioNet:', 'nethub:')
            content = content.replace('Nionet:', 'nethub:')

            # 4. Tag de imagem (CI publica :latest, :beta-prov, :VERSION e :sha).
            # Beta: sempre :beta-prov. Stable: versão informada (ex. 2.58.0) para
            # avançar ou voltar; sem versão, :stable (último ponteiro promovido).
            channel = getattr(provedor, 'release_channel', None) if provedor else None
            explicit = (image_tag or '').strip()
            if channel == 'beta':
                provider_tag = 'beta-prov'
            elif explicit:
                provider_tag = explicit
            else:
                provider_tag = 'stable'
            content = content.replace('${PROVIDER_IMAGE_TAG:-stable}', provider_tag)

            return content
        except Exception as e:
            logger.error(f"Erro ao preparar docker-compose: {e}")
            raise

    def deploy_provider_stack(self, provedor, image_tag=None):
        """
        Cria ou atualiza a Stack do provedor no Portainer remoto.
        image_tag: pin de versão no canal stable (ex. 2.58.0). Beta ignora e usa :beta-prov.
        """
        # Garante que a Registry do GitHub está configurada na VPS
        self._ensure_registry()
        # Garante que a rede overlay nethub existe no swarm antes do deploy
        self._ensure_network('nethub')
        
        subdomain = provedor.subdomain
        if not subdomain:
            logger.error(f"Provedor {provedor.nome} não tem subdomínio definido.")
            return False

        slug = subdomain.split('.')[0]
        stack_name = f"niohub-{slug}"
        
        try:
            if not (provedor.integration_token or '').strip():
                provedor.integration_token = secrets.token_urlsafe(32)
                provedor.save(update_fields=['integration_token'])
            compose_content = self._prepare_compose(
                subdomain, provedor, stack_name, image_tag=image_tag
            )

            # Verificar se a stack já existe
            list_url = f"{self.api_url}/api/stacks"
            res = requests.get(list_url, headers=self.headers, timeout=10, verify=False)
            if res.status_code != 200:
                logger.error(f"Erro ao listar stacks do Portainer ({res.status_code}): {res.text}")
                return False
                
            stacks = res.json()
            if not isinstance(stacks, list):
                logger.error(f"Resposta inesperada do Portainer (não é uma lista): {stacks}")
                return False
            
            # Log de debug para ver quais stacks vieram
            stack_names = [s.get('Name') for s in stacks]
            logger.info(f"Stacks existentes no Portainer: {stack_names}")
            
            existing_stack = next((s for s in stacks if s.get('Name') == stack_name), None)

            if existing_stack:
                # UPDATE STACK
                logger.info(f"Atualizando stack existente: {stack_name}")
                stack_id = existing_stack['Id']
                # pullImage=true na URL força o Portainer a baixar a imagem nova do Registry (GHCR)
                update_url = (
                    f"{self.api_url}/api/stacks/{stack_id}"
                    f"?endpointId={self.endpoint_id}&pullImage=true&forceRecreate=true"
                )
                existing_env = existing_stack.get('Env')
                payload = {
                    "stackFileContent": compose_content,
                    "env": self._get_env_vars(provedor, slug, stack_name=stack_name, existing_env=existing_env),
                    "prune": True,
                    "pullImage": True
                }
                
                response = requests.put(update_url, json=payload, headers=self.headers, timeout=90, verify=False)
            else:
                # CREATE STACK
                swarm_id = self._get_swarm_id()
                
                if swarm_id:
                    logger.info(f"Criando nova stack (Modo Swarm): {stack_name}")
                    create_url = f"{self.api_url}/api/stacks/create/swarm/string?endpointId={self.endpoint_id}&pullImage=true"
                    payload = {
                        "name": stack_name,
                        "swarmID": swarm_id,
                        "stackFileContent": compose_content,
                        "env": self._get_env_vars(provedor, slug, stack_name=stack_name, existing_env=None),
                        "pullImage": True
                    }
                else:
                    logger.info(f"Criando nova stack (Modo Standalone): {stack_name} (SwarmID não detectado)")
                    create_url = f"{self.api_url}/api/stacks/create/standalone/string?endpointId={self.endpoint_id}&pullImage=true"
                    payload = {
                        "name": stack_name,
                        "stackFileContent": compose_content,
                        "env": self._get_env_vars(provedor, slug, stack_name=stack_name, existing_env=None),
                        "pullImage": True
                    }
                
                response = requests.post(create_url, json=payload, headers=self.headers, timeout=60, verify=False)

            if response.status_code in [200, 201]:
                logger.info(f"Deploy concluído com sucesso para {stack_name} na VPS {self.vps.name}")
                return True
            else:
                logger.error(f"Erro no Portainer ({response.status_code}): {response.text}")
                # Log do payload para debug em caso de erro (omitindo segredos sensíveis)
                logger.debug(f"Payload enviado: {json.dumps({k:v for k,v in payload.items() if k != 'stackFileContent'})}")
                return False

        except Exception as e:
            logger.error(f"Falha crítica no deploy do Portainer: {e}", exc_info=True)
            return False

    def _docker_url(self, path: str) -> str:
        return f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/{path.lstrip('/')}"

    def wait_stack_running(self, stack_name: str, timeout_sec: int = 90) -> bool:
        """Espera a stack ter pelo menos um container running antes de limpar os exited."""
        import time

        deadline = time.monotonic() + max(15, int(timeout_sec))
        filters = json.dumps({"label": [f"com.docker.stack.namespace={stack_name}"]})
        while time.monotonic() < deadline:
            try:
                res = requests.get(
                    self._docker_url("containers/json"),
                    headers=self.headers,
                    params={"filters": filters},
                    timeout=15,
                    verify=False,
                )
                if res.status_code == 200:
                    running = res.json() or []
                    if isinstance(running, list) and len(running) >= 1:
                        logger.info(
                            "[cleanup] stack %s com %s container(s) running",
                            stack_name,
                            len(running),
                        )
                        return True
            except Exception as exc:
                logger.warning("[cleanup] wait_stack_running %s: %s", stack_name, exc)
            time.sleep(4)
        logger.warning("[cleanup] timeout aguardando stack %s running", stack_name)
        return False

    def prune_exited_containers(self) -> dict:
        """
        Remove containers parados (exited) na VPS para liberar RAM/disco
        antes do próximo provedor.
        """
        removed = 0
        try:
            res = requests.post(
                self._docker_url("containers/prune"),
                headers=self.headers,
                json={},
                timeout=45,
                verify=False,
            )
            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                ids = data.get("ContainersDeleted") or data.get("containersDeleted") or []
                removed = len(ids) if isinstance(ids, list) else 0
                logger.info(
                    "[cleanup] prune exited na VPS %s: %s container(s)",
                    getattr(self.vps, "name", "?"),
                    removed,
                )
                return {"ok": True, "removed": removed}
        except Exception as exc:
            logger.warning("[cleanup] containers/prune falhou: %s", exc)

        try:
            res = requests.get(
                self._docker_url("containers/json"),
                headers=self.headers,
                params={"all": 1, "filters": json.dumps({"status": ["exited", "dead"]})},
                timeout=20,
                verify=False,
            )
            if res.status_code != 200:
                return {"ok": False, "removed": 0, "error": f"list {res.status_code}"}
            containers = res.json() or []
            for c in containers:
                cid = c.get("Id")
                if not cid:
                    continue
                del_url = self._docker_url(f"containers/{cid}")
                dres = requests.delete(
                    del_url,
                    headers=self.headers,
                    params={"v": 1, "force": True},
                    timeout=20,
                    verify=False,
                )
                if dres.status_code in (200, 204, 404):
                    removed += 1
            logger.info(
                "[cleanup] remove exited manual na VPS %s: %s",
                getattr(self.vps, "name", "?"),
                removed,
            )
            return {"ok": True, "removed": removed}
        except Exception as exc:
            logger.warning("[cleanup] fallback remove exited: %s", exc)
            return {"ok": False, "removed": removed, "error": str(exc)[:200]}

    def prune_dangling_images(self) -> None:
        """Remove imagens dangling (digest antigo após pull da tag nova)."""
        try:
            requests.post(
                self._docker_url("images/prune"),
                headers=self.headers,
                params={"filters": json.dumps({"dangling": ["true"]})},
                timeout=60,
                verify=False,
            )
        except Exception as exc:
            logger.warning("[cleanup] images/prune: %s", exc)

    @staticmethod
    def _is_niohub_chat_image(repo_tags) -> bool:
        """Imagens do produto (ex.: ghcr.io/juniorssilvaa/niohub_chat-backend:2.61.0)."""
        if not repo_tags:
            return False
        for tag in repo_tags:
            if not isinstance(tag, str):
                continue
            lower = tag.lower()
            if "niohub_chat-" in lower or "niohub-chat-" in lower:
                return True
        return False

    def prune_unused_niohub_images(self, keep_tags=None) -> dict:
        """
        Remove imagens niohub_chat marcadas como Unused no Docker Desktop:
        tags antigas (ex. 2.60.0 / 2.61.0) que nenhum container está usando.

        Mantém imagens referenciadas por qualquer container e tags de ponteiro
        (stable / latest / beta-prov) quando ainda apontam para uma imagem em uso
        — na prática, só apaga o que o Docker considera não usada.
        """
        keep_tags = {str(t).strip().lower() for t in (keep_tags or []) if str(t).strip()}
        keep_tags |= {"stable", "latest", "beta-prov"}
        removed = 0
        skipped = 0
        errors = []

        try:
            cres = requests.get(
                self._docker_url("containers/json"),
                headers=self.headers,
                params={"all": 1},
                timeout=30,
                verify=False,
            )
            if cres.status_code != 200:
                return {"ok": False, "removed": 0, "error": f"containers {cres.status_code}"}

            used_ids = set()
            for c in cres.json() or []:
                img_id = (c.get("ImageID") or c.get("Image") or "").strip()
                if img_id:
                    # Normaliza sha256:abc e ids truncados
                    used_ids.add(img_id)
                    if img_id.startswith("sha256:"):
                        used_ids.add(img_id[7:])
                        used_ids.add(img_id[7:19])
                    else:
                        used_ids.add(img_id[:12])

            ires = requests.get(
                self._docker_url("images/json"),
                headers=self.headers,
                params={"all": 1},
                timeout=45,
                verify=False,
            )
            if ires.status_code != 200:
                return {"ok": False, "removed": 0, "error": f"images {ires.status_code}"}

            for img in ires.json() or []:
                repo_tags = img.get("RepoTags") or []
                if not self._is_niohub_chat_image(repo_tags):
                    continue

                img_id = (img.get("Id") or "").strip()
                if not img_id:
                    continue

                id_variants = {img_id}
                if img_id.startswith("sha256:"):
                    digest = img_id[7:]
                    id_variants.add(digest)
                    id_variants.add(digest[:12])
                else:
                    id_variants.add(img_id[:12])

                if id_variants & used_ids:
                    skipped += 1
                    continue

                # Preferir apagar por tag (libera o "Unused" sem derrubar imagem em uso)
                tags_to_delete = [t for t in repo_tags if isinstance(t, str) and t != "<none>:<none>"]
                if not tags_to_delete:
                    tags_to_delete = [img_id]

                for ref in tags_to_delete:
                    # Não remove ponteiros se ainda forem a única referência — mas se a
                    # imagem inteira está unused, apagar stable antigo é o desejado.
                    tag_part = ref.rsplit(":", 1)[-1].lower() if ":" in ref else ""
                    if tag_part in keep_tags and len(tags_to_delete) == 1:
                        # Ponteiro órfão unused: ainda remove (Unused no Desktop)
                        pass
                    try:
                        from urllib.parse import quote

                        # Docker API exige encoding do nome (ghcr.io/org/img:tag)
                        encoded_ref = quote(ref, safe="")
                        dres = requests.delete(
                            self._docker_url(f"images/{encoded_ref}"),
                            headers=self.headers,
                            params={"force": False},
                            timeout=45,
                            verify=False,
                        )
                        if dres.status_code in (200, 201, 404):
                            removed += 1
                            logger.info(
                                "[cleanup] imagem unused removida na VPS %s: %s",
                                getattr(self.vps, "name", "?"),
                                ref,
                            )
                        elif dres.status_code == 409:
                            skipped += 1
                        else:
                            errors.append(f"{ref}:{dres.status_code}")
                    except Exception as exc:
                        errors.append(f"{ref}:{exc}")

            # Segunda passagem: dangling gerados ao desatribuir tags
            self.prune_dangling_images()

            logger.info(
                "[cleanup] unused niohub_chat na VPS %s: removed=%s skipped=%s errors=%s",
                getattr(self.vps, "name", "?"),
                removed,
                skipped,
                len(errors),
            )
            return {
                "ok": True,
                "removed": removed,
                "skipped": skipped,
                "errors": errors[:10],
            }
        except Exception as exc:
            logger.warning("[cleanup] prune_unused_niohub_images: %s", exc)
            return {"ok": False, "removed": removed, "error": str(exc)[:200]}

    def settle_and_cleanup(self, stack_name: str) -> dict:
        """
        Após o redeploy: espera a stack nova subir, apaga containers exited,
        imagens dangling e tags niohub_chat Unused (versões antigas).
        Só então o lote deve ir para o próximo provedor.
        """
        import time

        time.sleep(8)
        running = self.wait_stack_running(stack_name, timeout_sec=90)
        pruned = self.prune_exited_containers()
        self.prune_dangling_images()
        unused = self.prune_unused_niohub_images()
        pruned["stack_running"] = running
        pruned["images_removed"] = unused.get("removed", 0)
        return pruned

    def _ensure_network(self, network_name='nethub'):
        """
        Garante que a rede overlay Swarm-scoped existe na VPS antes do deploy.
        Se não existir, cria automaticamente via Docker Engine (proxy Portainer).
        A rede precisa ser 'overlay' e 'attachable' para funcionar com Swarm stacks.
        """
        try:
            # 1. Listar redes via Docker Engine proxy do Portainer
            nets_url = f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/networks"
            res = requests.get(nets_url, headers=self.headers, timeout=10, verify=False)
            if res.status_code != 200:
                logger.warning(f"Não foi possível listar redes Docker ({res.status_code}). Tentando continuar...")
                return

            networks = res.json()
            # A resposta pode ser lista ou dict (Portainer < vs >= 2.20)
            if isinstance(networks, dict):
                networks = list(networks.values())

            # Verificar se já existe (por nome)
            existing = next(
                (n for n in networks if n.get('Name') == network_name),
                None
            )

            if existing:
                scope = existing.get('Scope', '')
                driver = existing.get('Driver', '')
                attachable = existing.get('Attachable', False)
                if driver == 'overlay':
                    logger.info(f"Rede '{network_name}' já existe e é overlay. OK.")
                    return
                else:
                    logger.warning(f"Rede '{network_name}' existe mas não é overlay ({driver}). Removendo para recriar...")
                    delete_url = f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/networks/{existing['Id']}"
                    res_del = requests.delete(delete_url, headers=self.headers, timeout=10, verify=False)
                    if res_del.status_code in [200, 204]:
                        import time
                        logger.info("Aguardando 3 segundos para propagação da remoção da rede...")
                        time.sleep(3)
                    else:
                        logger.error(f"Falha ao remover rede antiga ({res_del.status_code}): {res_del.text}")
                        return

            # 2. Criar a rede overlay swarm-scoped
            logger.info(f"Criando rede overlay Swarm '{network_name}'...")
            create_url = f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/networks/create"
            payload = {
                "Name": network_name,
                "Driver": "overlay",
                "CheckDuplicate": True,
                "Internal": False,
                "Attachable": True,
                "IPAM": {
                    "Config": [{"Subnet": "172.28.0.0/16", "Gateway": "172.28.0.1"}]
                }
            }
            res_create = requests.post(create_url, json=payload, headers=self.headers, timeout=15, verify=False)
            if res_create.status_code in [200, 201]:
                net_id = res_create.json().get('Id', '?')
                logger.info(f"Rede '{network_name}' criada com sucesso! ID={net_id}")
            else:
                # Se falhar com IPAM, tenta sem IPAM fixo
                payload.pop('IPAM')
                res_create = requests.post(create_url, json=payload, headers=self.headers, timeout=15, verify=False)
                if res_create.status_code in [200, 201]:
                    logger.info(f"Rede '{network_name}' criada com sucesso (IPAM automático)!")
                else:
                    logger.error(f"Falha ao criar rede '{network_name}' ({res_create.status_code}): {res_create.text}")
        except Exception as e:
            logger.error(f"Erro ao garantir rede '{network_name}': {e}")


    def _get_env_vars(self, provedor, slug, stack_name=None, existing_env=None):
        """
        Gera a lista de variáveis de ambiente para a stack.

        Em *update* de stack existente, repõe POSTGRES_PASSWORD / DATABASE_URL / SECRET_KEY
        a partir do env já guardado no Portainer. O volume do Postgres só aceita a senha
        definida na primeira subida; gerar senha nova em cada deploy quebra o login.

        No Docker Swarm, o DNS interno usa o nome «{stack}_{serviço}» (ex.: niohub-foo_postgres).
        """
        import os
        import secrets
        from urllib.parse import quote_plus

        existing = {}
        if existing_env:
            for item in existing_env:
                if isinstance(item, dict) and item.get('name'):
                    existing[item['name']] = item.get('value') or ''

        db_name = f"niochat_{slug}"
        db_user = f"niochat_{slug}"
        epass = existing.get('POSTGRES_PASSWORD')
        edb = existing.get('POSTGRES_DB')
        if epass and edb == db_name:
            db_pass = epass
            if existing.get('POSTGRES_USER'):
                db_user = existing['POSTGRES_USER']
            logger.info(
                'Reutilizando credenciais Postgres da stack no Portainer (volume já inicializado).'
            )
        else:
            db_pass = secrets.token_urlsafe(16)

        secret_key = existing.get('SECRET_KEY') or secrets.token_urlsafe(32)
        pg_host = f'{stack_name}_postgres' if stack_name else 'postgres'
        database_url = (
            f'postgresql://{quote_plus(db_user)}:{quote_plus(db_pass)}'
            f'@{pg_host}:5432/{db_name}'
        )
        
        # Redis do tenant é 100% isolado por stack (service `redis` + rede `internal`).
        # Nunca apontar para redis compartilhado da VPS para evitar vazamento entre provedores.
        redis_host = f'{stack_name}_redis' if stack_name else 'redis'
        redis_pass = (existing.get('REDIS_PASSWORD') or '').strip()
        if not redis_pass:
            redis_pass = secrets.token_urlsafe(16)

        # RabbitMQ ainda pode ser infra compartilhada (vps.rabbitmq_url). Se estiver vazio,
        # tenta descobrir via API do Portainer.
        # ⚠️ O default antigo do modelo era localhost — isso quebra o tenant em produção (dramatiq_config).
        rabbitmq_url = (self.vps.rabbitmq_url or '').strip()

        def _rabbitmq_url_is_loopback(url: str) -> bool:
            if not url:
                return False
            try:
                from urllib.parse import urlparse
                h = urlparse(url).hostname
                return h in ('localhost', '127.0.0.1', '::1')
            except Exception:
                return False

        if _rabbitmq_url_is_loopback(rabbitmq_url):
            logger.warning(
                'VPS id=%s: rabbitmq_url aponta para localhost (legado ou cópia errada de .env). '
                'Tratando como vazio para usar «rabbitmq» na rede Docker.',
                getattr(self.vps, 'pk', None),
            )
            rabbitmq_url = ''

        if not rabbitmq_url:
            logger.info("RabbitMQ não configurado na VPS (ou inválido). Auto-descoberta via Portainer...")
            rabbitmq_url = self._discover_rabbitmq_amqp_url()
            if rabbitmq_url:
                self.vps.rabbitmq_url = rabbitmq_url
                self.vps.save(update_fields=['rabbitmq_url'])
                logger.info("RabbitMQ detectado na infra e salvo em VpsServer.rabbitmq_url.")

        rabbitmq_url = rabbitmq_url or 'amqp://guest:guest@rabbitmq:5672/'

        existing_dramatiq = (existing.get('DRAMATIQ_BROKER_URL') or '').strip()
        dramatiq_broker_url = existing_dramatiq or rabbitmq_url
        if not dramatiq_broker_url:
            dramatiq_broker_url = 'amqp://guest:guest@rabbitmq:5672/'

        telegram_api_id = os.getenv('TELEGRAM_API_ID', '')
        telegram_api_hash = os.getenv('TELEGRAM_API_HASH', '')
        
        subdomain = provedor.subdomain or ""
        base_url = f"https://{subdomain}"

        # Credenciais do primeiro admin no painel do provedor:
        # 1) Portainer já tem INITIAL_* (redeploy) → manter
        # 2) Senha definida no superadmin ao criar user ligado ao provedor → campo encriptado no Provedor
        # 3) Fallback legado
        from ..panel_bootstrap_crypto import decrypt_bootstrap_safe

        initial_username = existing.get('INITIAL_ADMIN_USERNAME') or self._resolve_initial_admin_username(
            provedor, slug
        )
        initial_email = existing.get('INITIAL_ADMIN_EMAIL') or self._resolve_initial_admin_email(
            provedor, slug
        )
        initial_password = (existing.get('INITIAL_ADMIN_PASSWORD') or '').strip()
        if not initial_password:
            initial_password = decrypt_bootstrap_safe(
                getattr(provedor, 'panel_bootstrap_password_ciphertext', '') or ''
            ).strip()
        if not initial_password:
            initial_password = 'NioChat@2024'

        # Montar a REDIS_URL
        redis_url = f"redis://:{redis_pass}@{redis_host}:6379/0"

        calls_api_key = (existing.get('NIOHUB_CALLS_API_KEY') or '').strip()
        if not calls_api_key:
            calls_api_key = secrets.token_urlsafe(32)

        calls_service = f'{stack_name}_niohub-calls' if stack_name else 'niohub-calls'
        backend_internal = f'{stack_name}_niochat-backend' if stack_name else 'niochat-backend'
        wacalls_pg_url = (
            f'postgresql://{quote_plus(db_user)}:{quote_plus(db_pass)}'
            f'@{pg_host}:5432/postgres?sslmode=disable'
        )
        wacalls_udp_port = (existing.get('WACALLS_UDP_PORT') or '').strip()
        if not wacalls_udp_port:
            # Porta única por provedor na mesma VPS (3478 + id evita conflito entre stacks)
            wacalls_udp_port = str(3478 + (int(provedor.id) % 1000))

        # Variáveis Fixas (Vem do .env do Superadmin ou Defaults fornecidos)
        # Atenção: os.getenv('X', default) NÃO usa default se X existir como string vazia
        # (comum no Portainer/compose com SUPABASE_URL=). Tratar '' como ausente.
        _DEFAULT_SUPABASE_URL = 'https://uousrmdefljusigvncrb.supabase.co'
        _DEFAULT_SUPABASE_ANON_KEY = (
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.'
            'eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVvdXNybWRlZmxqdXNpZ3ZuY3JiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk5ODQyODgsImV4cCI6MjA3NTU2MDI4OH0.'
            '_DLHRiae-1eVA31SpPl-M36D12HH5G7jmylIRLKyZ_I'
        )

        def _nonempty(*candidates, fallback=''):
            for c in candidates:
                if c is None:
                    continue
                s = str(c).strip()
                if s:
                    return s
            return fallback

        supabase_url = _nonempty(
            existing.get('SUPABASE_URL'),
            os.getenv('SUPABASE_URL'),
            fallback=_DEFAULT_SUPABASE_URL,
        )
        supabase_key = _nonempty(
            existing.get('SUPABASE_ANON_KEY'),
            os.getenv('SUPABASE_ANON_KEY'),
            fallback=_DEFAULT_SUPABASE_ANON_KEY,
        )
        whatsapp_token = _nonempty(
            existing.get('WHATSAPP_SYSTEM_USER_TOKEN'),
            os.getenv('WHATSAPP_SYSTEM_USER_TOKEN'),
            fallback='EAAKI9ZAACsD0BQVz1PTZAiQqhXwkVapWERoqfyjuZCIFp71w4v7YzzQAOZCw6Rlqk3IPoZCLmKbIFHY5gCnuEtb41z4D1R2KivGliWfu6zSIBvL0UaQ8mdSDDxpBlaCfBFp7uPxnog7uCmZBmL4yenS31Hi7cSTkZBD3olET3DdRZBed1HvJUwDpZCZB8zXEW2U0MKyAZDZD',
        )
        whatsapp_verify = _nonempty(
            existing.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN'),
            os.getenv('WHATSAPP_WEBHOOK_VERIFY_TOKEN'),
            fallback='niochat_webhook_verify_token',
        )
        fb_secret = _nonempty(
            existing.get('FACEBOOK_APP_SECRET'),
            os.getenv('FACEBOOK_APP_SECRET'),
            fallback='3436ab37c90d49673af2865a9d995102',
        )
        instagram_app_id = _nonempty(
            existing.get('INSTAGRAM_APP_ID'),
            os.getenv('INSTAGRAM_APP_ID'),
            fallback='',
        )
        instagram_app_secret = _nonempty(
            existing.get('INSTAGRAM_APP_SECRET'),
            os.getenv('INSTAGRAM_APP_SECRET'),
            fallback='',
        )
        sentry_dsn = _nonempty(
            existing.get('SENTRY_DSN'),
            os.getenv('SENTRY_DSN'),
            fallback='https://63ab1fa0b722f15ce12d2eabe231cc9a@o4510794514366464.ingest.de.sentry.io/4510794516136016',
        )
        env_vars = [
            {"name": "ENVIRONMENT", "value": "production"},
            {"name": "DEBUG", "value": "False"},
            {"name": "SUBDOMAIN", "value": subdomain},
            {
                "name": "TRAEFIK_ROUTER_PREFIX",
                "value": f"niohub-{slug}",
            },
            {"name": "TRAEFIK_RULE_FE", "value": f"Host(`{subdomain}`)"},
            {
                "name": "TRAEFIK_RULE_API",
                "value": f"Host(`{subdomain}`) && PathPrefix(`/api/`)",
            },
            {
                "name": "TRAEFIK_RULE_WS",
                "value": f"Host(`{subdomain}`) && PathPrefix(`/ws/`)",
            },
            {
                "name": "TRAEFIK_RULE_HOOKS",
                "value": f"Host(`{subdomain}`) && PathPrefix(`/webhooks/`)",
            },
            {"name": "SECRET_KEY", "value": secret_key},
            
            # Banco de Dados
            {"name": "POSTGRES_DB", "value": db_name},
            {"name": "POSTGRES_USER", "value": db_user},
            {"name": "POSTGRES_PASSWORD", "value": db_pass},
            {"name": "POSTGRES_HOST", "value": pg_host},
            {"name": "POSTGRES_PORT", "value": "5432"},
            {"name": "DATABASE_URL", "value": database_url},
            {"name": "DOCKER_STACK_NAME", "value": stack_name or ""},
            
            # Redis
            {"name": "REDIS_HOST", "value": redis_host},
            {"name": "REDIS_PASSWORD", "value": redis_pass},
            {"name": "REDIS_URL", "value": redis_url},
            {"name": "REDIS_PORT", "value": "6379"},
            {"name": "REDIS_DB", "value": "0"},
            {"name": "REDIS_AI_DB", "value": "1"},
            {"name": "REDIS_CONVERSATION_DB", "value": "2"},
            {"name": "REDIS_CACHE_DB", "value": "3"},
            {"name": "REDIS_CONNECTION_POOL_SIZE", "value": "20"},
            {"name": "REDIS_SOCKET_TIMEOUT", "value": "10"},
            {"name": "REDIS_SOCKET_CONNECT_TIMEOUT", "value": "10"},
            {"name": "REDIS_RETRY_ON_TIMEOUT", "value": "True"},
            {"name": "REDIS_HEALTH_CHECK_INTERVAL", "value": "30"},
            
            # Supabase (sempre injetado — URL/anon key compartilhados entre tenants)
            {"name": "SUPABASE_URL", "value": supabase_url},
            {"name": "SUPABASE_ANON_KEY", "value": supabase_key},
            {"name": "SUPABASE_ENABLED", "value": "True"},
            {"name": "SUPABASE_AUDIT_TABLE", "value": "auditoria"},
            {"name": "SUPABASE_MESSAGES_TABLE", "value": "mensagens"},
            {"name": "SUPABASE_CSAT_TABLE", "value": "csat_feedback"},
            {"name": "SUPABASE_CONTACTS_TABLE", "value": "contacts"},
            {"name": "SUPABASE_CONVERSATIONS_TABLE", "value": "conversations"},
            
            # RabbitMQ / Dramatiq
            {"name": "DRAMATIQ_BROKER_URL", "value": dramatiq_broker_url},

            # Telegram (credenciais centralizadas no superadmin)
            {"name": "TELEGRAM_API_ID", "value": telegram_api_id},
            {"name": "TELEGRAM_API_HASH", "value": telegram_api_hash},
            
            # WhatsApp / Facebook / Instagram (credenciais centralizadas no superadmin)
            {"name": "WHATSAPP_SYSTEM_USER_TOKEN", "value": whatsapp_token},
            {"name": "WHATSAPP_WEBHOOK_VERIFY_TOKEN", "value": whatsapp_verify},
            {"name": "FACEBOOK_APP_SECRET", "value": fb_secret},
            {"name": "INSTAGRAM_APP_ID", "value": instagram_app_id},
            {"name": "INSTAGRAM_APP_SECRET", "value": instagram_app_secret},
            
            # Sentry
            {"name": "SENTRY_DSN", "value": sentry_dsn},
            {"name": "SENTRY_TEST_KEY", "value": "teste-sentry-niochat"},
            
            # Frontend / CORS
            {"name": "VITE_ENV", "value": "production"},
            {"name": "VITE_API_URL", "value": base_url},
            {"name": "VITE_SUPABASE_URL", "value": supabase_url},
            {"name": "VITE_SUPABASE_ANON_KEY", "value": supabase_key},

            # Integração com Superadmin (Centralização de Webhooks)
            {"name": "SUPERADMIN_ID_PROVEDOR_API", "value": os.getenv('SUPERADMIN_ID_PROVEDOR_API', 'https://app.niohub.com.br')},
            {"name": "SUPERADMIN_API_URL", "value": os.getenv('SUPERADMIN_ID_PROVEDOR_API', 'https://app.niohub.com.br')},
            {"name": "SUPERADMIN_PROVEDOR_ID", "value": str(provedor.id)},
            {"name": "SUPERADMIN_PROVIDER_TOKEN", "value": (provedor.integration_token or '').strip()},
            {"name": "ADMIN_WEBHOOK_SECRET", "value": os.getenv('ADMIN_WEBHOOK_SECRET', '') or (SystemConfig.objects.first().payload.get('ADMIN_WEBHOOK_SECRET', '') if SystemConfig.objects.first() and SystemConfig.objects.first().payload else '')},

            # AwesomeAPI — cotação USD-BRL (Meta Analytics)
            {"name": "AWESOMEAPI_TOKEN", "value": (SystemConfig.objects.first().payload.get('awesomeapi_token', '') if SystemConfig.objects.first() and isinstance(SystemConfig.objects.first().payload, dict) else '') or os.getenv('AWESOMEAPI_TOKEN', '')},

            # NioHub Calls — voz WhatsApp (Go + Postgres da stack)
            {"name": "NIOHUB_CALLS_BASE_URL", "value": f"http://{calls_service}:8080"},
            {"name": "NIOHUB_CALLS_API_KEY", "value": calls_api_key},
            {
                "name": "NIOHUB_CALLS_WEBHOOK_SELF_URL",
                # URL pública: host Docker Swarm (stack_servico) tem "_" e o Django rejeita no Host header.
                "value": base_url,
            },
            {"name": "WACALLS_PG_URL", "value": wacalls_pg_url},
            {"name": "WACALLS_PG_NAMESPACE", "value": existing.get('WACALLS_PG_NAMESPACE') or 'niohub_calls'},
            {"name": "WACALLS_MAX_CALLS", "value": existing.get('WACALLS_MAX_CALLS') or '8'},
            {"name": "WACALLS_PUBLIC_IP", "value": existing.get('WACALLS_PUBLIC_IP') or 'auto'},
            {"name": "WACALLS_UDP_PORT", "value": wacalls_udp_port},
            
            # Primeiro utilizador no Postgres do tenant (ensure_provider_admin no entrypoint)
            {"name": "INITIAL_ADMIN_USERNAME", "value": initial_username},
            {"name": "INITIAL_ADMIN_EMAIL", "value": initial_email},
            {"name": "INITIAL_ADMIN_PASSWORD", "value": initial_password},
            
            {"name": "ALLOWED_HOSTS", "value": f"127.0.0.1,localhost,{subdomain}"},
            {"name": "CORS_ALLOWED_ORIGINS", "value": f"{base_url},https://app.niohub.com.br"},
            {"name": "CSRF_TRUSTED_ORIGINS", "value": f"{base_url},https://app.niohub.com.br"},
            
            # Security
            {"name": "SECURE_CONTENT_TYPE_NOSNIFF", "value": "True"},
            {"name": "SECURE_BROWSER_XSS_FILTER", "value": "True"},
            {"name": "SECURE_SSL_REDIRECT", "value": "False"},
            {"name": "SESSION_COOKIE_SECURE", "value": "False"},
            {"name": "CSRF_COOKIE_SECURE", "value": "False"},
        ]
        
        return env_vars

    def _resolve_initial_admin_username(self, provedor, slug):
        """
        Retorna o username do usuário admin inicial do provedor.
        Prioridade:
          1. User vinculado ao provedor no banco do superadmin
          2. Slug do subdomínio (ex: 'provedor1') — sempre preenchido
        """
        linked_user = (
            User.objects.filter(provedor=provedor)
            .order_by("id")
            .first()
        )
        if linked_user and linked_user.username:
            return linked_user.username.strip()
        # Fallback: slug do subdomínio (ex.: suporte.niohub.com.br → suporte)
        return slug

    def _resolve_initial_admin_email(self, provedor, slug):
        """
        Retorna o email do usuário admin inicial do provedor.
        Prioridade:
          1. Email do User vinculado ao provedor
          2. email_contato do Provedor
          3. email gerado a partir do slug
        """
        linked_user = (
            User.objects.filter(provedor=provedor)
            .order_by("id")
            .first()
        )
        if linked_user and linked_user.email:
            return linked_user.email.strip()
        if provedor.email_contato:
            return provedor.email_contato
        # Fallback final: gera email padrão
        return f"{slug}@niohub.com.br"

    def _get_swarm_id(self):
        """
        Busca o Swarm ID consultando a API do Docker Engine através do proxy do Portainer.
        """
        try:
            # Estratégia 1: Consultar /info do Docker Engine via proxy do Portainer
            docker_info_url = f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/info"
            res_info = requests.get(docker_info_url, headers=self.headers, timeout=10, verify=False)
            
            if res_info.status_code == 200:
                data = res_info.json()
                # No Docker Info, o Swarm ID fica em Swarm -> Cluster -> ID
                swarm_id = data.get('Swarm', {}).get('Cluster', {}).get('ID')
                
                if swarm_id:
                    logger.info(f"SwarmID detectado via Docker Info: {swarm_id}")
                    return swarm_id
                else:
                    logger.error(f"Docker Info retornou sucesso, mas sem Swarm Cluster ID. O nó é um Swarm Manager?")
            else:
                logger.error(f"Erro ao acessar Docker Info ({res_info.status_code}): {res_info.text}")
                
            # Estratégia 2: Fallback para a rota /api/swarm do Portainer (se disponível)
            swarm_url = f"{self.api_url}/api/swarm?endpointId={self.endpoint_id}"
            res_swarm = requests.get(swarm_url, headers=self.headers, timeout=10, verify=False)
            if res_swarm.status_code == 200:
                swarm_id = res_swarm.json().get('ID')
                if swarm_id:
                    logger.info(f"SwarmID detectado via /api/swarm: {swarm_id}")
                    return swarm_id

        except Exception as e:
            logger.warning(f"Não foi possível obter SwarmID: {e}")
            
        logger.error("Falha ao detectar SwarmID em todas as tentativas.")
        return ""

    @staticmethod
    def _parse_docker_env_list(env_list):
        """Parse KEY=value lines (valor pode conter '=')."""
        out = {}
        for raw in env_list or []:
            if not raw or '=' not in raw:
                continue
            k, v = raw.split('=', 1)
            out[k.strip()] = v
        return out

    def _discover_rabbitmq_from_swarm_services(self):
        """
        Fallback: inspecionar serviços Swarm cujo nome contém 'rabbitmq' (Portainer /docker/services).
        """
        from urllib.parse import quote_plus

        try:
            urls_to_try = (
                f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/services/json",
                f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/services",
            )
            raw_list = None
            for svc_url in urls_to_try:
                res = requests.get(svc_url, headers=self.headers, timeout=20, verify=False)
                if res.status_code != 200:
                    continue
                raw = res.json()
                if isinstance(raw, list):
                    raw_list = raw
                elif isinstance(raw, dict):
                    raw_list = raw.get('Services') or raw.get('services') or raw.get('data')
                    if raw_list is None and isinstance(raw.get('message'), str):
                        continue
                if raw_list is not None:
                    break
            if not raw_list:
                return ''
            for svc in raw_list:
                name = (svc.get('Spec', {}) or {}).get('Name', '') or ''
                if 'rabbitmq' not in name.lower():
                    continue
                env_list = (
                    (svc.get('Spec', {}) or {})
                    .get('TaskTemplate', {})
                    .get('ContainerSpec', {})
                    .get('Env', [])
                )
                envd = self._parse_docker_env_list(env_list)
                user = (envd.get('RABBITMQ_DEFAULT_USER') or '').strip()
                pwd = (envd.get('RABBITMQ_DEFAULT_PASS') or '').strip()
                if not user:
                    logger.warning(
                        "RabbitMQ service %s não tem RABBITMQ_DEFAULT_USER no Swarm spec. "
                        "Configure essas vars no docker-compose do RabbitMQ ou defina "
                        "rabbitmq_url manualmente no VpsServer do Superadmin.",
                        name,
                    )
                    continue
                url = f'amqp://{quote_plus(user)}:{quote_plus(pwd)}@rabbitmq:5672/'
                logger.info(
                    "RabbitMQ auto-detectado via Swarm service %s (user=%s)", name, user
                )
                return url
        except Exception as e:
            logger.warning("Auto RabbitMQ (Swarm services): %s", e)
        return ''

    def _discover_rabbitmq_amqp_url(self):
        """
        Infere DRAMATIQ_BROKER_URL examinando a stack do RabbitMQ já existente na VPS.
        O hostname é sempre «rabbitmq» (alias na rede nethub), coerente com o compose do broker.
        """
        import json
        from urllib.parse import quote_plus

        try:
            list_url = f"{self.api_url}/api/stacks"
            res = requests.get(list_url, headers=self.headers, timeout=20, verify=False)
            if res.status_code != 200:
                logger.warning("Auto RabbitMQ: listar stacks falhou (%s)", res.status_code)
                return self._discover_rabbitmq_from_swarm_services()

            stacks = res.json() or []
            rb_stacks = [s for s in stacks if 'rabbitmq' in (s.get('Name') or '').lower()]
            if not rb_stacks:
                logger.info("Auto RabbitMQ: nenhuma stack com 'rabbitmq' no nome; tentando services Swarm.")
                return self._discover_rabbitmq_from_swarm_services()

            for rb_stack in rb_stacks:
                namespace = rb_stack.get('Name')
                if not namespace:
                    continue
                c_url = f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/containers/json"
                params = {"filters": json.dumps({"label": [f"com.docker.stack.namespace={namespace}"]})}
                res_c = requests.get(c_url, params=params, headers=self.headers, timeout=20, verify=False)
                if res_c.status_code != 200:
                    continue
                containers = res_c.json() or []
                if not containers:
                    continue

                def _is_rabbit_image(c):
                    im = (c.get('Image') or '').lower()
                    return 'rabbitmq' in im

                ordered = sorted(containers, key=lambda c: (0 if _is_rabbit_image(c) else 1))
                for c in ordered:
                    c_id = c.get('Id')
                    if not c_id:
                        continue
                    inspect_url = (
                        f"{self.api_url}/api/endpoints/{self.endpoint_id}/docker/containers/{c_id}/json"
                    )
                    res_i = requests.get(inspect_url, headers=self.headers, timeout=20, verify=False)
                    if res_i.status_code != 200:
                        continue
                    env_list = res_i.json().get('Config', {}).get('Env', [])
                    envd = self._parse_docker_env_list(env_list)
                    user = envd.get('RABBITMQ_DEFAULT_USER')
                    pwd = envd.get('RABBITMQ_DEFAULT_PASS')
                    if not user and not pwd and not _is_rabbit_image(c):
                        continue
                    if not user:
                        logger.warning(
                            "RabbitMQ container %s… na stack %s não tem "
                            "RABBITMQ_DEFAULT_USER nas variáveis de ambiente inspecionadas. "
                            "Verifique se a stack do RabbitMQ declara essas vars no docker-compose. "
                            "Configure rabbitmq_url manualmente na VPS no Superadmin se necessário.",
                            c_id[:12],
                            namespace,
                        )
                        continue
                    url = (
                        f'amqp://{quote_plus(user.strip())}:{quote_plus((pwd or "").strip())}'
                        f'@rabbitmq:5672/'
                    )
                    logger.info(
                        "RabbitMQ auto-detectado na stack %s (container %s… user=%s)",
                        namespace,
                        c_id[:12],
                        user.strip(),
                    )
                    return url

            return self._discover_rabbitmq_from_swarm_services()
        except Exception as e:
            logger.error("Auto RabbitMQ: %s", e)
            return self._discover_rabbitmq_from_swarm_services()

    def _ensure_registry(self):
        """
        Verifica se a Registry do GHCR (GitHub) está configurada no Portainer.
        Se não estiver, cria automaticamente.
        """
        try:
            # 1. Tentar buscar credenciais dinâmicas do Banco de Dados
            from super_core.models import SystemConfig
            import os
            
            config = SystemConfig.objects.first()
            
            # Fallbacks (Env)
            username = os.getenv('GITHUB_USERNAME', '')
            password = os.getenv('GHCR_TOKEN', '')

            if config and config.payload:
                username = config.payload.get('github_username', username)
                password = config.payload.get('github_pat', password)

            # 2. Listar Registries no Portainer
            reg_url = f"{self.api_url}/api/registries"
            res = requests.get(reg_url, headers=self.headers, timeout=10, verify=False)
            if res.status_code != 200:
                logger.error(f"Erro ao listar registries: {res.text}")
                return

            registries = res.json()
            # Procurar por ghcr.io
            gh_reg = next((r for r in registries if r.get('URL') == 'ghcr.io'), None)

            if not gh_reg:
                logger.info(f"Configurando Registry do GitHub ({username}) automaticamente...")
                # 3. Criar Registry
                payload = {
                    "Name": "GitHub GHCR",
                    "Type": 3, # Custom Registry (conforme log do usuário)
                    "URL": "ghcr.io",
                    "Authentication": True,
                    "Username": username,
                    "Password": password
                }
                res_create = requests.post(reg_url, json=payload, headers=self.headers, timeout=10, verify=False)
                if res_create.status_code in [200, 201]:
                    logger.info("Registry do GitHub configurada com sucesso!")
                else:
                    logger.error(f"Falha ao criar Registry no Portainer: {res_create.text}")
            else:
                # Opcional: Atualizar a senha se ela mudou no banco? 
                # Por enquanto apenas logamos que já existe.
                logger.debug("Registry do GitHub já está configurada.")
        except Exception as e:
            logger.error(f"Erro ao garantir Registry no Portainer: {e}")
