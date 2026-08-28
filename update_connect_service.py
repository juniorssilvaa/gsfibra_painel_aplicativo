"""
Actualiza o serviço niohub-meta-connect-frontend na stack do superadmin no Portainer.
Faz pull da imagem mais recente (niohub_chat-frontend:stable) e recria o serviço.

  $env:PORTAINER_API_KEY = "ptr_..."
  python update_connect_service.py

Opcional:
  PORTAINER_URL         (default: https://portainer-vps1.niohub.com.br)
  SUPERADMIN_STACK_NAME (default: superadmin)
  CONNECT_SERVICE_NAME  (default: niohub-meta-connect-frontend)
  PROVIDER_IMAGE_TAG    (default: stable)
"""
import os
import sys
import warnings

import requests

warnings.filterwarnings("ignore")

PORTAINER_URL = os.environ.get("PORTAINER_URL", "https://portainer-vps1.niohub.com.br").rstrip("/")
API_KEY = os.environ.get("PORTAINER_API_KEY", "")
SUPERADMIN_STACK_NAME = os.environ.get("SUPERADMIN_STACK_NAME", "superadmin")
CONNECT_SERVICE_NAME = os.environ.get("CONNECT_SERVICE_NAME", "niohub-meta-connect-frontend")
PROVIDER_IMAGE_TAG = os.environ.get("PROVIDER_IMAGE_TAG", "stable")
COMPOSE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "superadmin",
    "docker-compose.superadmin.yml",
)


def main() -> int:
    if not API_KEY:
        print("ERRO: defina PORTAINER_API_KEY no ambiente.")
        return 1

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    print("1. Buscando stacks em Portainer...")
    res = requests.get(f"{PORTAINER_URL}/api/stacks", headers=headers, verify=False, timeout=30)
    if res.status_code != 200:
        print(f"ERRO ao listar stacks ({res.status_code}): {res.text[:400]}")
        return 1

    stacks = res.json()
    for s in stacks:
        print(f"   Stack: {s['Name']} (ID: {s['Id']}, EndpointId: {s['EndpointId']})")

    target = next((s for s in stacks if s["Name"] == SUPERADMIN_STACK_NAME), None)
    if not target:
        nomes = [s["Name"] for s in stacks]
        print(f"ERRO: Stack '{SUPERADMIN_STACK_NAME}' não encontrada. Stacks disponíveis: {nomes}")
        print("  Defina SUPERADMIN_STACK_NAME=<nome correcto>")
        return 1

    stack_id = target["Id"]
    endpoint_id = target["EndpointId"]
    print(f"\n2. Stack: {SUPERADMIN_STACK_NAME}  ID={stack_id}  EndpointId={endpoint_id}")

    if not os.path.isfile(COMPOSE_PATH):
        print(f"ERRO: Compose não encontrado: {COMPOSE_PATH}")
        return 1

    print(f"3. Lendo {COMPOSE_PATH} ...")
    with open(COMPOSE_PATH, encoding="utf-8") as f:
        compose_content = f.read()

    compose_content = compose_content.replace(
        "niohub_chat-frontend:stable",
        f"niohub_chat-frontend:{PROVIDER_IMAGE_TAG}",
    )
    print(f"   Tag da imagem connect: {PROVIDER_IMAGE_TAG}")

    env_vars = target.get("Env") or []
    print(f"   Mantendo env da stack ({len(env_vars)} vars).")

    print("\n4. Actualizando stack do superadmin (pull + prune)...")
    update_url = f"{PORTAINER_URL}/api/stacks/{stack_id}?endpointId={endpoint_id}&pullImage=true"
    payload = {
        "stackFileContent": compose_content,
        "env": env_vars,
        "prune": True,
        "pullImage": True,
    }
    res_update = requests.put(update_url, json=payload, headers=headers, verify=False, timeout=180)

    if res_update.status_code == 200:
        print("\n[OK] Stack do superadmin actualizada.")
        print(f"     O serviço '{CONNECT_SERVICE_NAME}' está agora com a imagem mais recente.")
        print("     O fluxo Meta (FINISH_REQUEST → tenant) funciona a partir de agora.")
        return 0

    print(f"\n[ERRO] ({res_update.status_code}): {res_update.text[:800]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
