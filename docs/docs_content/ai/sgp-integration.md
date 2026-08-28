# Integração SGP

Documentação sobre a integração do NioChat com o Sistema de Gestão de Provedores (SGP).

## Visão Geral

A IA do NioChat possui integração com o SGP para realizar operações como:
- Consulta de clientes e contratos
- Verificação de acesso à internet
- Criação de chamados técnicos
- Geração de segunda via de fatura
- Liberação por confiança

## Tipos de Ocorrência

A IA utiliza **dois tipos de ocorrência** ao criar chamados técnicos no SGP:

### Tipo 1 - Sem Acesso à Internet (Padrão)

**Código:** `1`

**Descrição:** Usado quando o cliente relata problemas de conectividade total ou problemas físicos no equipamento.

**Palavras-chave que acionam este tipo:**
- `sem internet`
- `sem acesso`
- `não funciona`
- `não conecta`
- `offline`
- `desconectado`
- `quebrou`
- `rompeu`
- `caiu`
- `drop`
- `fio quebrado`
- `cabo quebrado`
- `LED vermelho` (indica problema físico)

**Exemplos de uso:**
- Cliente relata: "Minha internet não funciona"
- Cliente relata: "O LED está vermelho"
- Cliente relata: "O cabo quebrou"

### Tipo 2 - Internet Lenta/Instável

**Código:** `2`

**Descrição:** Usado quando o cliente relata problemas de velocidade ou instabilidade na conexão.

**Palavras-chave que acionam este tipo:**
- `lenta`
- `lento`
- `devagar`
- `baixa velocidade`
- `velocidade baixa`
- `ping alto`
- `lag`
- `travando`
- `instável`

**Exemplos de uso:**
- Cliente relata: "A internet está muito lenta"
- Cliente relata: "Está travando muito"
- Cliente relata: "A velocidade está baixa"

## Detecção Automática

A IA detecta automaticamente o tipo de ocorrência baseado no relato do cliente:

1. **Análise do texto:** A IA analisa o motivo e sintomas relatados pelo cliente
2. **Busca por palavras-chave:** Verifica se há palavras-chave relacionadas a cada tipo
3. **Priorização:** 
   - Se encontrar palavras de "internet lenta" → Tipo 2
   - Se encontrar palavras de "sem acesso" → Tipo 1
   - Se houver menção a LED vermelho → Tipo 1 (problema físico)
   - Padrão: Tipo 1 (sem acesso)

## Localização no Código

A lógica de detecção está implementada em:

**Arquivo:** `backend/core/openai_service.py`

**Linhas:** 1267-1307

```python
# Detectar tipo de ocorrência automaticamente baseado no relato
ocorrenciatipo = 1  # Padrão: sem acesso à internet

# Palavras-chave para internet lenta
palavras_lenta = ['lenta', 'lento', 'devagar', 'baixa velocidade', ...]

# Palavras-chave para sem acesso
palavras_sem_acesso = ['sem internet', 'sem acesso', 'não funciona', ...]

# Verificação e atribuição do tipo
if any(palavra in texto_completo for palavra in palavras_lenta):
    ocorrenciatipo = 2  # Internet lenta
elif any(palavra in texto_completo for palavra in palavras_sem_acesso):
    ocorrenciatipo = 1  # Sem acesso à internet
```

## Função da IA

A IA possui uma função específica para criar chamados técnicos:

**Nome da função:** `criar_chamado_tecnico`

**Descrição:** Abrir chamado técnico no SGP com detecção automática do tipo de problema.

**Parâmetros:**
- `cpf_cnpj`: CPF ou CNPJ do cliente
- `motivo`: Motivo do chamado técnico
- `sintomas`: Sintomas relatados pelo cliente

**Uso:** A IA usa esta função APENAS quando:
- Cliente confirmar LEDs vermelhos piscando
- Problema físico identificado
- Necessidade real de visita técnica

## API SGP

O método que envia o chamado para o SGP está em:

**Arquivo:** `backend/core/sgp_client.py`

**Método:** `criar_chamado(contrato, ocorrenciatipo, conteudo)`

**Parâmetros:**
- `contrato`: ID do contrato
- `ocorrenciatipo`: Código do tipo de ocorrência (1 ou 2)
- `conteudo`: Conteúdo principal do chamado

## Observações Importantes

1. **Padrão:** Se a IA não conseguir detectar claramente o tipo, usa o **Tipo 1** (sem acesso) como padrão
2. **LED Vermelho:** Sempre classifica como Tipo 1, pois indica problema físico
3. **Detecção por contexto:** A IA analisa o contexto completo do relato, não apenas palavras isoladas
4. **Expansão futura:** O sistema pode ser expandido para suportar mais tipos de ocorrência conforme necessário

## Exemplos Práticos

### Exemplo 1: Sem Acesso
```
Cliente: "Minha internet não funciona, o LED está vermelho"
IA detecta: Tipo 1 (Sem acesso)
Chamado criado com ocorrenciatipo = 1
```

### Exemplo 2: Internet Lenta
```
Cliente: "A internet está muito lenta, travando muito"
IA detecta: Tipo 2 (Internet lenta)
Chamado criado com ocorrenciatipo = 2
```

### Exemplo 3: Indefinido
```
Cliente: "Tenho um problema com a internet"
IA detecta: Tipo 1 (Padrão - sem acesso)
Chamado criado com ocorrenciatipo = 1
```
