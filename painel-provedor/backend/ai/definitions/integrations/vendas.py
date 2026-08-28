"""Definitions ERP — vendas."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.vendas import consulta_viabilidade


def register():
    register_tool(
        name="consulta_viabilidade",
        handler=consulta_viabilidade,
        description=(
            "Consulta viabilidade tecnica de instalacao. Duas formas validas: "
            "(1) pin de localizacao do WhatsApp (latitude+longitude) OU "
            "(2) endereco escrito: nome da rua/avenida (logradouro) e/ou CEP — "
            "pelo menos um dos dois e obrigatorio na busca por escrito. "
            "Quando o cliente quiser contratar e ainda nao informou dados, peca as DUAS opcoes "
            "(localizacao atual pelo WhatsApp OU rua/CEP). "
            "Se a mensagem tiver latitude e longitude, chame ESTA tool AGORA com esses campos. "
            "Se tiver nome da rua e/ou CEP, chame ESTA tool AGORA com logradouro e/ou cep — nao espere o pin. "
            "Nao responda em texto sem chamar a tool quando ja houver pin, rua ou CEP. "
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
                    "description": "Nome da rua/avenida (obrigatorio na busca por escrito se nao houver CEP).",
                },
                "numero_inicial": {
                    "type": "string",
                    "description": "Numero inicial da consulta (ou o numero unico do endereco).",
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
                    "description": "CEP (com ou sem mascara). Obrigatorio na busca por escrito se nao houver logradouro.",
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
                    "description": "Alternativa no formato 'lat,lng'.",
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
