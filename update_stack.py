"""
Uso local: envia o compose de painel-provedor para uma stack já existente no Portainer.

O env da stack no Portainer mantém-se (SUBDOMAIN, TRAEFIK_*, Postgres, etc.) — costuma
vir do primeiro deploy pelo superadmin na nuvem. Este script só troca o YAML e a tag
de imagem (PROVIDER_IMAGE_TAG).

Opcional no Portainer (espera pelo PostgreSQL no entrypoint):
  POSTGRES_WAIT_MAX_SECONDS=300 (default), POSTGRES_WAIT_SLEEP_SECONDS=2,
  POSTGRES_WAIT_SKIP=1 (saltar espera, ex. BD externa).
  Em Swarm, se «postgres» não resolver DNS, o serviço postgres tem de estar na mesma
  stack/rede overlay que o backend; alinhar DATABASE_URL (host) com esse nome.

  $env:PORTAINER_API_KEY = "ptr_..."
  $env:STACK_NAME = "niohub-e-tech"   # nome da stack no Portainer
  python update_stack.py

Opcional: PORTAINER_URL, PROVIDER_IMAGE_TAG (default stable / beta-prov).
"""
import os
import re
import sys
import warnings

import requests

warnings.filterwarnings("ignore")

PORTAINER_URL = os.environ.get(
    "PORTAINER_URL", "https://portainer-vps1.niohub.com.br"
).rstrip("/")
API_KEY = os.environ.get("PORTAINER_API_KEY", "")
STACK_NAME = os.environ.get("STACK_NAME", "niohub-teste")
PROVIDER_IMAGE_TAG = os.environ.get("PROVIDER_IMAGE_TAG", "stable")
COMPOSE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "painel-provedor",
    "docker-compose.yml",
)


def prepare_compose(raw: str) -> str:
    """Ajustes mínimos para Swarm multi-tenant (sem porta 5432 no host, sem aliases)."""
    content = raw
    content = re.sub(r"^\s*container_name:.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*aliases:.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*-\s*niochat_postgres.*$", "", content, flags=re.MULTILINE)
    content = re.sub(
        r'^\s*ports:.*?\n\s*-\s*"5432:5432".*?\n',
        "\n",
        content,
        flags=re.DOTALL | re.MULTILINE,
    )
    content = content.replace("${PROVIDER_IMAGE_TAG:-stable}", PROVIDER_IMAGE_TAG)
    return content


def main() -> int:
    if not API_KEY:
        print("ERRO: defina PORTAINER_API_KEY no ambiente.")
        return 1

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    print("1. Buscando stacks...")
    res = requests.get(f"{PORTAINER_URL}/api/stacks", headers=headers, verify=False, timeout=30)
    if res.status_code != 200:
        print(f"ERRO ao listar stacks ({res.status_code}): {res.text[:400]}")
        return 1

    stacks = res.json()
    if not isinstance(stacks, list):
        print(f"ERRO: resposta inesperada: {type(stacks)}")
        return 1

    for s in stacks:
        print(f"   Stack: {s['Name']} (ID: {s['Id']}, EndpointId: {s['EndpointId']})")

    target = next((s for s in stacks if s["Name"] == STACK_NAME), None)
    if not target:
        print(f"ERRO: Stack '{STACK_NAME}' não encontrada.")
        return 1

    stack_id = target["Id"]
    endpoint_id = target["EndpointId"]
    print(f"\n2. Stack: {STACK_NAME}  ID={stack_id}  EndpointId={endpoint_id}")

    if not os.path.isfile(COMPOSE_PATH):
        print(f"ERRO: Compose não encontrado: {COMPOSE_PATH}")
        return 1

    print(f"3. Lendo {COMPOSE_PATH} ...")
    with open(COMPOSE_PATH, encoding="utf-8") as f:
        raw = f.read()
    new_compose = prepare_compose(raw)
    print(f"   Compose ({len(new_compose)} chars), tag imagem: {PROVIDER_IMAGE_TAG}")

    print("\n4. Imagens:")
    for line in new_compose.split("\n"):
        if "image:" in line and "ghcr.io" in line:
            print(f"   {line.strip()}")

    env_vars = target.get("Env") or []
    print(f"\n5. Mantendo env da stack no Portainer ({len(env_vars)} vars).")

    print("\n6. Atualizando stack (pull + prune)...")
    update_url = (
        f"{PORTAINER_URL}/api/stacks/{stack_id}"
        f"?endpointId={endpoint_id}&pullImage=true"
    )
    payload = {
        "stackFileContent": new_compose,
        "env": env_vars,
        "prune": True,
        "pullImage": True,
    }
    res_update = requests.put(
        update_url, json=payload, headers=headers, verify=False, timeout=120
    )

    if res_update.status_code == 200:
        print("   [OK] Stack atualizada.")
        return 0

    print(f"   [ERRO] ({res_update.status_code}): {res_update.text[:800]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
