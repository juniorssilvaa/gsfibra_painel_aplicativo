"""Definitions — tools ACS/TR-069 (Wi-Fi)."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.acs import alterar_wifi_acs, consultar_wifi_acs


def register():
    register_tool(
        name="consultar_wifi_acs",
        handler=consultar_wifi_acs,
        description=(
            "Consulta Wi-Fi do modem/ONT (SSID 2.4/5G, status, hosts). "
            "Fluxo: se ainda nao buscou o cliente, peca CPF/CNPJ e chame buscar_cliente antes. "
            "Use o pppoe_login salvo no estado (nao peca login PPPoE ao cliente). "
            "Nunca invente SSID."
        ),
        parameters={
            "type": "object",
            "properties": {
                "login": {
                    "type": "string",
                    "description": "Login PPPoE do buscar_cliente/estado (opcional se ja estiver salvo).",
                },
                "device_id": {
                    "type": "string",
                    "description": "Identificador ACS do equipamento, se conhecido.",
                },
            },
            "required": [],
        },
        tags=["acs", "wifi", "suporte", "integrations"],
        permissions=["consulta"],
        source="niohub",
        aliases=["consultar_wifi", "consultar_ssid"],
    )
    register_tool(
        name="alterar_wifi_acs",
        handler=alterar_wifi_acs,
        description=(
            "Altera nome da rede (SSID) e/ou senha Wi-Fi via ACS/TR-069. "
            "Fluxo obrigatorio quando o cliente pedir troca de senha ou nome do Wi-Fi: "
            "1) peca CPF/CNPJ; 2) buscar_cliente; 3) use pppoe_login do retorno/estado; "
            "4) se for NOME: peca o novo nome e a banda (2.4/5/ambas); "
            "5) se for SENHA: peca senha com NO MAXIMO 8 caracteres, letra maiuscula, "
            "minuscula e um caractere especial, e a banda; "
            "6) chame esta tool. "
            "Nunca diga que alterou sem chamar a tool. Nao mencione ACS/TR-069."
        ),
        parameters={
            "type": "object",
            "properties": {
                "login": {
                    "type": "string",
                    "description": "Login PPPoE do buscar_cliente/estado (opcional se ja estiver salvo).",
                },
                "device_id": {
                    "type": "string",
                    "description": "Identificador ACS do equipamento, se conhecido.",
                },
                "band": {
                    "type": "string",
                    "description": 'Banda: "24", "5" ou "both".',
                },
                "ssid_24": {
                    "type": "string",
                    "description": "Novo nome da rede Wi-Fi 2.4 GHz.",
                },
                "ssid_5": {
                    "type": "string",
                    "description": "Novo nome da rede Wi-Fi 5 GHz.",
                },
                "pass_24": {
                    "type": "string",
                    "description": "Nova senha 2.4 GHz (máx. 8; maiúscula+minúscula+especial).",
                },
                "pass_5": {
                    "type": "string",
                    "description": "Nova senha 5 GHz (máx. 8; maiúscula+minúscula+especial).",
                },
                "aplicar_nas_duas": {
                    "type": "boolean",
                    "description": "Se true e so ssid_24 vier, aplica o mesmo nome no 5G.",
                },
            },
            "required": [],
        },
        tags=["acs", "wifi", "suporte", "integrations"],
        permissions=["alteracao"],
        source="niohub",
        aliases=["alterar_wifi", "trocar_senha_wifi", "trocar_ssid", "alterar_ssid"],
    )
