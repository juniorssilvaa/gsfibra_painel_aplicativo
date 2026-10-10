"""Definitions ERP — vendas."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.vendas import consulta_viabilidade


def register():
    register_tool(
        name="consulta_viabilidade",
        handler=consulta_viabilidade,
        description=(
            "Consulta viabilidade tecnica de instalacao. Exige CEP OU localizacao exata: "
            "(1) pin de localizacao do WhatsApp (latitude+longitude), "
            "(2) CEP, ou (3) link da localizacao do Google Maps (passe o link em 'coordenada'). "
            "Rua, bairro e numero da casa sozinhos NAO bastam: peca com gentileza o pin, o CEP "
            "ou o link do Google Maps. Com CEP, envie tambem numero e rua se o cliente informou. "
            "Se a mensagem tiver pin, coordenadas, link do Google Maps ou CEP, chame ESTA tool AGORA. "
            "Nao responda em texto sem chamar a tool quando ja houver pin, link ou CEP. "
            "Se tem_viabilidade=true, confirme cobertura e continue. "
            "Se tem_viabilidade=false, informe sem cobertura e ofereca transferir para a equipe comercial. "
            "Nunca invente cobertura. "
            "Se a tool retornar viabilidade_indisponivel=true, siga EXATAMENTE a 'nota' retornada: "
            "nao mencione ao cliente nada sobre configuracao, sistema ou indisponibilidade — apenas "
            "colete endereco/ponto de referencia e siga o atendimento normalmente, como se a consulta "
            "nunca tivesse sido chamada."
        ),
        parameters={
            "type": "object",
            "properties": {
                "logradouro": {
                    "type": "string",
                    "description": (
                        "Complemento do CEP: somente o nome da rua/avenida, sem numero, bloco, "
                        "apartamento, bairro ou CEP."
                    ),
                },
                "numero_inicial": {
                    "type": "string",
                    "description": "Somente o numero da casa/predio (ex.: '191'), sem bloco ou apartamento.",
                },
                "numero_final": {
                    "type": "string",
                    "description": "Numero final da consulta (igual ao inicial se for um unico numero).",
                },
                "bairro": {
                    "type": "string",
                    "description": "Bairro do endereco.",
                },
                "cep": {
                    "type": "string",
                    "description": (
                        "CEP (com ou sem mascara), mesmo que o cliente tenha enviado no meio de um texto longo. "
                        "Obrigatorio quando nao houver pin/coordenadas."
                    ),
                },
                "cidade": {
                    "type": "string",
                    "description": "Cidade do endereco.",
                },
                "latitude": {
                    "type": "string",
                    "description": "Latitude do ponto (obrigatorio quando o cliente enviou localizacao).",
                },
                "longitude": {
                    "type": "string",
                    "description": "Longitude do ponto (obrigatorio quando o cliente enviou localizacao).",
                },
                "coordenada": {
                    "type": "string",
                    "description": "Alternativa no formato 'lat,lng' ou o link da localizacao do Google Maps enviado pelo cliente.",
                },
            },
            "required": [],
        },
        tags=["vendas", "integrations", "erp", "viabilidade"],
        erp=["sgp"],
        permissions=["consulta"],
        source="integrations",
        aliases=["consultar_viabilidade"],
    )
