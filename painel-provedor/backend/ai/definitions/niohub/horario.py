"""Definitions NioHub — hora atual e horário de atendimento."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.horario import consultar_hora_atual, consultar_horario_atendimento


def register():
    register_tool(
        name="consultar_hora_atual",
        handler=consultar_hora_atual,
        description=(
            "Consulta a hora atual no fuso do provedor. "
            "Use SEMPRE antes de saudar ou se despedir (Bom dia / Boa tarde / Boa noite) "
            "e ao montar mensagens de encerramento. "
            "Retorna saudacao e despedida corretas para o horário. "
            "Nao use esta tool para horario de funcionamento da loja/empresa."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        tags=["horario", "niohub", "atendimento"],
        permissions=["consulta"],
        source="niohub",
    )
    register_tool(
        name="consultar_horario_atendimento",
        handler=consultar_horario_atendimento,
        description=(
            "Consulta o horario de funcionamento/atendimento configurado no painel do provedor. "
            "Use SEMPRE quando o cliente perguntar horario de funcionamento, "
            "horario de atendimento, que horas abre/fecha ou se esta aberto. "
            "Nunca invente horarios — chame esta tool."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        tags=["horario", "niohub", "atendimento", "funcionamento"],
        permissions=["consulta"],
        source="niohub",
    )
