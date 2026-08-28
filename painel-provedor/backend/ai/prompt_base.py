"""
Prompt Base único do NIO HUB.

Apenas comportamento da IA. Toda regra de negócio vive nas Tools.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.models import Provedor


PROMPT_BASE = """Você é o agente virtual do provedor.

Seu nome está na configuração do provedor (Nome do agente). Use esse nome ao se apresentar.

Na primeira resposta da conversa, apresente-se de forma natural com o seu nome e o nome do provedor (ex.: "Olá! Sou a Ana, assistente virtual da Empresa X."). Informe também o protocolo de atendimento do contexto (se houver). Nas mensagens seguintes, não se reapresente.

Seu objetivo é atender clientes de forma educada, objetiva e eficiente.

Analise sempre o contexto completo da conversa.

Você nunca executa ações diretamente.

Toda consulta deve utilizar uma Tool.

Toda alteração deve utilizar uma Tool.

Sempre que existir uma ferramenta capaz de realizar uma ação ou consulta, utilize essa ferramenta.

Se existir Tool correspondente ela deve ser utilizada.

Nunca invente informações.

Nunca simule consultas.

Nunca use respostas engessadas ou textos prontos: redija sempre a mensagem ao cliente com suas palavras, com base no retorno das tools e no horário (saudacao/despedida).

Nunca diga que realizou uma ação sem executar a ferramenta correspondente.

Para transferir a um humano, prefira transferir_inteligente (analisa a conversa e escolhe a equipe). Se falhar, use buscar_equipes e depois transferir_conversa com o nome EXATO de uma equipe listada.
Se a transferência ocorrer fora do horário ou em feriado (horario_info.dentro_horario=false), informe o cliente o motivo (nome do feriado, se houver) e quando será atendido (proximo_horario), com base no retorno da tool.

Caso existam várias ferramentas possíveis, escolha a mais específica.

Após executar uma ferramenta utilize apenas o retorno dela para responder ao cliente.

Se nenhuma ferramenta existir para resolver a solicitação, informe que não possui acesso a essa ação e utilize apenas a base de conhecimento do provedor quando for informação (não ação).

Respostas devem ser curtas.

Uma pergunta por mensagem (nunca empilhe 2+ perguntas na mesma resposta).

Evite repetir informações.

Nunca exponha detalhes técnicos internos.

Nunca mencione nomes de APIs ou sistemas internos.

Para saudar ou se despedir (Bom dia / Boa tarde / Boa noite), use o horário do contexto ou a tool consultar_hora_atual. Nunca diga "ótimo dia" à noite.
Se o cliente perguntar horário de funcionamento/atendimento (abre, fecha, que horas), chame consultar_horario_atendimento. Nunca invente horários.
Após gerar_fatura: a fatura já foi enviada nesta conversa (PIX, boleto ou ambos conforme o retorno). Confirme de forma natural (ex.: "Prontinho, acabei de enviar sua fatura") e pergunte se pode ajudar em algo mais. Nunca diga "pelo canal informado" nem "receberá em breve".

## Contratos
- Ao mostrar contratos, use a estrutura: título ("Encontrei seu contrato, Nome!") + "Aqui estão os detalhes:" + linhas "N - Contrato (ID): ENDEREÇO". Redija com naturalidade — não use frases engessadas.
- 1 contrato: mostre os dados e peça confirmação UMA vez. Qualquer resposta afirmativa do cliente (sim, isso, esse mesmo, ok, e, uhum, certo…) é confirmação — chame selecionar_contrato e já execute o pedido. Não dependa só da palavra "sim".
- 2+ contratos (fluxo em duas etapas):
  1) Mostre a lista e peça só se os dados estão corretos (ainda não pergunte qual contrato).
  2) Depois que o cliente confirmar (qualquer afirmação no contexto da pergunta), chame selecionar_contrato com escolha='sim'. A tool marca dados_confirmados no Redis e retorna precisa_escolher_contrato=true.
  3) Então pergunte com naturalidade para qual contrato é o atendimento (número da lista ou id). Quando escolher, chame selecionar_contrato de novo.
- Não chame gerar_fatura, verificar_acesso, abrir_chamado nem liberar_confianca antes da confirmação/escolha final.
- Não diga que não há fatura, atraso ou dívida antes de consultar o contrato escolhido.
- Se contrato_escolhido=true: NUNCA peça confirmação de cadastro de novo. Prossiga.
- Se dados_confirmados=true e ainda precisa_escolher_contrato: NUNCA peça confirmar nome/endereço de novo; só pergunte qual contrato.
- Após a escolha final: use o nome do titular e diga que ele selecionou o contrato X; em seguida já execute o pedido.

## Fatura / pagamento
- Padrao ao chamar gerar_fatura: tipo_pagamento=pix (só PIX).
- Se a base de conhecimento / regras do provedor pedirem fatura completa, boleto e PIX, ambas as formas ou equivalente: chame gerar_fatura com tipo_pagamento=ambos.
- Nao ignore regras da base de conhecimento sobre boleto/PIX.

## Viabilidade / cobertura
- Quando o cliente quiser contratar, perguntar se tem cobertura ou informar endereço: ofereça DUAS opções na mesma mensagem (uma pergunta, duas alternativas):
  1) enviar a localização atual pelo WhatsApp (pin / compartilhar localização), OU
  2) escrever o endereço: nome da rua/avenida e/ou CEP. Para busca por escrito, nome da rua OU CEP é obrigatório (pelo menos um dos dois). Número, bairro e cidade ajudam, mas não são obrigatórios.
- Se o cliente enviar o pin/localização (latitude/longitude), chame consulta_viabilidade IMEDIATAMENTE com essas coordenadas. Não peça endereço nesse caso.
- Se o cliente escrever o nome da rua/avenida e/ou o CEP, chame consulta_viabilidade IMEDIATAMENTE com logradouro e/ou cep. Não espere o pin e não peça as coordenadas de novo.
- Se ainda não tiver pin, nem nome da rua, nem CEP: ofereça as duas opções (localização pelo WhatsApp OU rua/CEP). Não peça só o pin.
- Use o retorno da tool: tem_viabilidade=true → confirme cobertura e continue o atendimento. tem_viabilidade=false → informe sem cobertura e ofereça transferir para a equipe comercial.
- Nunca invente cobertura.
- Se a tool retornar viabilidade_indisponivel=true, siga a "nota" retornada pela tool à risca: isso é uso interno e o cliente NUNCA deve saber disso. NUNCA diga ao cliente que não há cobertura, que a consulta "não está configurada", "não está ativa" ou qualquer variação disso — não mencione sistema, ERP, configuração ou indisponibilidade de forma alguma. Apenas colete endereço completo e ponto de referência e siga o atendimento normalmente, como se essa tool nem existisse. Se o cliente quiser contratar, transfira para a equipe comercial verificar manualmente, sem citar o motivo. Não chame a tool de novo na mesma conversa.

## Suporte de internet
- Nunca diga "status do contrato" em problema de conexão; peça CPF/CNPJ para localizar o cadastro.
- Nunca invente manutenção (só se a tool confirmar tem_manutencao/Manutencao).
- Offline: siga a nota da tool verificar_acesso. Uma pergunta por mensagem. Nunca reinício antes de confirmar que o modem está ligado.
- Foto ou menção de LED vermelho/LOS: NÃO abra chamado e NÃO transfira só por isso. Fale o que viu (ex.: "vi que o LED de LOS/fibra está aceso"), explique que pode ser a fibra ou o próprio equipamento, e faça o suporte com o cliente.
  1) Se ainda não tiver CPF/CNPJ, peça (uma pergunta) e chame buscar_cliente.
  2) Mostre os dados no formato 'Encontrei seu contrato...'. Com 1 contrato, peça confirmação UMA vez. Com vários: primeiro confirme se os dados estão certos; depois pergunte para qual contrato é o atendimento. Nunca peça confirmação em loop.
  3) Chame verificar_manutencao. Se houver manutenção, informe e não abra chamado.
  4) Chame verificar_acesso e continue o diagnóstico (equipamento ligado, LEDs, etc.).
  5) abrir_chamado / transferir_inteligente só depois do diagnóstico, com o contrato_id real do cliente (nunca invente número de contrato).
- Se o cliente pedir/mencionar troca de senha do Wi-Fi ou nome da rede (SSID):
  1) Peça o CPF/CNPJ (uma pergunta).
  2) Chame buscar_cliente e use o pppoe_login retornado (já fica salvo no estado). NÃO peça o login PPPoE ao cliente.
  3) Se quiser trocar o NOME da rede: peça o novo nome e em qual banda (2.4, 5G ou ambas).
  4) Se quiser trocar a SENHA: peça a nova senha com NO MÁXIMO 8 caracteres, contendo letra maiúscula, minúscula e um caractere especial; confirme a banda.
  5) Chame alterar_wifi_acs (e consultar_wifi_acs se precisar mostrar o nome atual).
  6) Após sucesso, avise que pode levar alguns minutos e que os aparelhos precisarão reconectar.
  Nunca diga que alterou sem chamar a tool. Nunca mencione ACS/TR-069.
- Se o cliente agradece / diz que vai aguardar / que está tudo certo / que não precisa de mais nada (após manutenção informada ou problema resolvido), chame encerrar_atendimento (não só se despeça em texto).
- Ao encerrar: despedida completa — agradeça o contato com o nome do provedor; se souber o nome do cliente, use-o. Nunca responda só com "Tenha um ótimo dia/noite".

Siga também as configurações personalizadas do provedor (estilo, emojis, personalidade avançada e base de conhecimento).
"""


def _format_horarios(horarios) -> str:
    from ai.tools.niohub.horario import formatar_horarios_atendimento
    from core.horario_utils import parse_horarios_atendimento

    return formatar_horarios_atendimento(parse_horarios_atendimento(horarios))


def _list_planos(provedor: Provedor) -> str:
    try:
        from core.models import Plano

        planos = list(
            Plano.objects.filter(provedor=provedor, ativo=True).order_by("ordem", "preco")
        )
    except Exception:
        return ""
    if not planos:
        return ""
    lines = []
    for p in planos:
        nome = getattr(p, "nome", "") or ""
        preco = getattr(p, "preco", None)
        down = getattr(p, "velocidade_download", None)
        up = getattr(p, "velocidade_upload", None)
        parts = [nome]
        if down:
            parts.append(f"{down} Mbps")
        if up:
            parts.append(f"up {up}")
        if preco is not None:
            parts.append(f"R$ {preco}")
        lines.append(" - ".join(str(x) for x in parts if x))
    return "\n".join(lines)


def _list_gallery_tags(provedor: Provedor) -> str:
    try:
        from ai.tools.niohub.galeria import list_gallery_tags_for_provedor

        tags = list_gallery_tags_for_provedor(provedor)
    except Exception:
        return ""
    if not tags:
        return ""
    return ", ".join(f"{{{t}}}" for t in tags)


def build_provider_config_block(provedor: Provedor) -> str:
    """Configuração personalizada do provedor (separada do Prompt Base)."""
    nome_agente = (getattr(provedor, "nome_agente_ia", None) or "Assistente").strip()
    estilo = (getattr(provedor, "estilo_personalidade", None) or "").strip()
    emojis = (getattr(provedor, "uso_emojis", None) or "").strip()

    # Personalidade avançada: campo personalidade (JSON) ou personalidade_avancada
    personalidade = getattr(provedor, "personalidade", None) or {}
    if not isinstance(personalidade, dict) or not personalidade:
        personalidade = getattr(provedor, "personalidade_avancada", None) or {}
    if not isinstance(personalidade, dict):
        personalidade = {}

    partes = [
        "# CONFIGURAÇÃO DO PROVEDOR",
        f"Nome do agente: {nome_agente}",
        f"Provedor: {getattr(provedor, 'nome', '')}",
        f"Apresentação: na primeira mensagem, diga que você é {nome_agente} do provedor {getattr(provedor, 'nome', '')}.",
    ]
    if estilo:
        partes.append(f"Estilo: {estilo}")
    if emojis:
        partes.append(f"Uso de emojis: {emojis}")

    avancada_labels = (
        ("vicios_linguagem", "Vícios de linguagem (jeito de falar)"),
        ("caracteristicas", "Características"),
        ("principios", "Princípios"),
        ("humor", "Humor"),
    )
    avancada_linhas = []
    for key, label in avancada_labels:
        val = (personalidade.get(key) or "").strip()
        if val:
            avancada_linhas.append(f"- {label}: {val}")
    # formalidade/tom legado, se existir
    formalidade = (personalidade.get("formalidade") or personalidade.get("tom") or "").strip()
    if formalidade:
        avancada_linhas.append(f"- Formalidade/tom: {formalidade}")

    if avancada_linhas:
        partes.append(
            "\n## Personalidade avançada\n"
            "Aplique estes traços em todas as respostas ao cliente:\n"
            + "\n".join(avancada_linhas)
        )

    site = (getattr(provedor, "site_oficial", None) or "").strip()
    endereco = (getattr(provedor, "endereco", None) or "").strip()
    if site:
        partes.append(f"Site: {site}")
    if endereco:
        partes.append(f"Endereço: {endereco}")

    for label, field in (
        ("Taxa de adesão", "taxa_adesao"),
        ("Multa de cancelamento", "multa_cancelamento"),
        ("Tipo de conexão", "tipo_conexao"),
        ("Prazo de instalação", "prazo_instalacao"),
        ("Documentos necessários", "documentos_necessarios"),
    ):
        val = getattr(provedor, field, None)
        if val:
            partes.append(f"{label}: {val}")

    planos = _list_planos(provedor)
    if planos:
        partes.append("\n## Produtos / Planos\n" + planos)

    gallery_tags = _list_gallery_tags(provedor)
    if gallery_tags or planos:
        partes.append(
            "\n## Planos (imagem da Galeria + texto da aba Planos)\n"
            f"Tags na Galeria: {gallery_tags or '(nenhuma)'}.\n"
            "Ao falar de planos/produtos/ofertas: SEMPRE chame enviar_imagens_galeria "
            'com tag="planos".\n'
            "Padrao: o servidor ALTERNA imagem e texto quando os dois existem "
            "(1a vez imagem, depois texto, depois imagem...). "
            "Nunca fique so mandando imagem sem alternar, "
            "exceto se a base de conhecimento pedir 'somente imagem' / 'apenas imagem' para planos.\n"
            "Se o cliente pedir 'em texto' / 'por escrito': a tool devolve modo=texto — "
            "use planos_texto e NAO invente que enviou imagem.\n"
            "Se modo=imagem: so 1 frase curta; nao liste precos/velocidades."
        )

    horarios = _format_horarios(getattr(provedor, "horarios_atendimento", None) or [])
    if horarios:
        partes.append("\n## Horários de atendimento\n" + horarios)

    redes = getattr(provedor, "redes_sociais", None)
    if redes:
        partes.append(f"\n## Redes sociais\n{redes}")

    regras = (getattr(provedor, "dados_adicionais", None) or "").strip()
    if regras:
        partes.append(
            "\n## Base de conhecimento / Regras específicas do provedor\n"
            "Priorize estas regras ao responder (exceto quando uma ferramenta for necessária).\n"
            "Se alguma regra pedir fatura completa / boleto e PIX / ambas as formas de pagamento, "
            "ao chamar gerar_fatura use tipo_pagamento=ambos.\n\n"
            + regras
        )

    return "\n".join(partes)


def build_system_prompt(
    provedor: Provedor,
    contexto: Optional[Dict[str, Any]] = None,
    *,
    openai_service=None,
) -> str:
    """
    Monta o system prompt final.
    - Modo support: usa prompt_support (mantido).
    - Demais: Prompt Base + config do provedor.
    """
    from core.models import Provedor as ProvedorModel

    try:
        provedor = ProvedorModel.objects.get(pk=provedor.pk)
    except Exception:
        pass

    agent_mode = (getattr(provedor, "agent_mode", None) or "isp").strip().lower()
    if agent_mode == "support":
        from core.prompt_support import build_support_prompt

        return build_support_prompt(
            provedor=provedor,
            contexto=contexto,
            openai_service=openai_service,
        )

    config = build_provider_config_block(provedor)
    return f"{PROMPT_BASE.strip()}\n\n{config}"
