# Análise: CPF correto mas nome de outra pessoa (GILBERTO SILVA x AMANDA DINIZ DE SOUZA)

## O que aconteceu

- Cliente informou CPF **700.179.490-25** (pertence a **AMANDA DINIZ DE SOUZA**).
- A IA exibiu nome **GILBERTO SILVA** e contrato (1499) com endereço RUA SARGENTO SILVIO HOLANDA 45...
- No sistema correto, esse CPF está vinculado a **AMANDA DINIZ DE SOUZA** (1 contrato ativo).

## Conclusão da análise

### 1. A IA **não** está alucinando

Quando o usuário envia CPF e a função `consultar_cliente_sgp` é chamada com sucesso, o backend **não** deixa a IA escrever a mensagem. O fluxo é:

1. Backend chama a API do SGP com o CPF.
2. Backend monta o texto da resposta com nome e contratos (**mensagem_formatada**).
3. Se houver `mensagem_formatada` e `cliente_encontrado`, o **openai_service** retorna esse texto **direto** para o usuário (sem passar pelo modelo).

Ou seja, o texto "GILBERTO SILVA, contrato localizado..." veio **100% do nosso código**, não da IA.

### 2. De onde vem o nome

O nome exibido era obtido **apenas** do **primeiro contrato** retornado pelo SGP:

- `nome = contratos[0].get('razaoSocial', '')`

Se a API do SGP devolver:

- nome do **titular do CPF** no nível da resposta (ex.: `razaoSocial`, `nome`, `nomeCliente`), ou
- e, em cada item de `contratos[]`, um `razaoSocial` que pode ser de outro titular (ex.: antigo responsável pelo contrato),

usar só `contratos[0].razaoSocial` pode mostrar o nome **errado** (ex.: GILBERTO SILVA em vez de AMANDA DINIZ DE SOUZA).

### 3. Não é dado fixo do prompt

Não há "GILBERTO SILVA" nem exemplos fixos de nome no prompt. O nome sempre veio dos dados retornados pela API do SGP (no caso, do primeiro contrato).

### 4. A consulta ao CPF/CNPJ é feita

O fluxo **sempre** chama o SGP com o CPF informado. Não há resposta sem consulta. O problema foi **qual** campo da resposta do SGP foi usado para o nome (só o do primeiro contrato).

---

## Ajustes feitos no código

### 1. Prioridade do nome do titular (ai_actions_handler.py)

- **Antes:** só `contratos[0].get('razaoSocial', '')`.
- **Agora:**
  1. Nome no **nível da resposta** do SGP: `razaoSocial`, `nome`, `nomeCliente` ou objeto `cliente` (com `razaoSocial`/`nome`).
  2. Se não houver, **fallback** para `contratos[0].get('razaoSocial', '')`.
  3. Se ainda não houver, usa `"Cliente"`.

Assim, se o SGP enviar o nome do titular (AMANDA DINIZ DE SOUZA) no nível da resposta, esse nome será usado; caso contrário, continuamos usando o do primeiro contrato.

### 2. Logs de diagnóstico

- **sgp_client.py:** ao retornar de `consultar_cliente`, loga as **chaves** da resposta e se existe nome no nível topo (`tem_nome_topo`), sem logar CPF/nome.
- **ai_actions_handler.py:** ao montar a mensagem, loga se o nome veio da resposta do SGP ou do primeiro contrato (`nome_resposta_sgp`, `nome_primeiro_contrato`).

Isso permite checar nas próximas ocorrências:
- O que o SGP está retornando (estrutura e se traz nome no topo).
- Se estamos usando nome do topo ou do contrato.

---

## O que fazer no SGP / integração

1. **Confirmar contrato da AMANDA:**  
   No SGP, para o CPF 700.179.490-25, verificar se o contrato 1499 e o endereço RUA SARGENTO SILVIO HOLANDA 45 estão corretos para **AMANDA DINIZ DE SOUZA** (e não para GILBERTO SILVA).

2. **Estrutura da API de consulta por CPF:**  
   Verificar se a API retorna o **nome do titular do CPF** no nível da resposta (ex.: `razaoSocial`, `nome` ou `nomeCliente`). Se retornar, o código já prioriza esse campo.

3. **Se o SGP não enviar nome no topo:**  
   Ajustar a API do SGP para incluir o nome do titular (do CPF) no nível da resposta, além dos contratos, para evitar usar o `razaoSocial` de um contrato que possa estar associado a outro nome.

---

## Resumo

| Pergunta                         | Resposta                                                                 |
|----------------------------------|---------------------------------------------------------------------------|
| A IA alucinou?                   | **Não.** O texto vem do backend com dados do SGP.                        |
| Usa dados fixos do prompt?       | **Não.** Nome sempre da resposta do SGP.                                 |
| Responde sem consultar CPF?      | **Não.** A consulta ao SGP com CPF é feita.                              |
| Origem do nome errado?           | Uso **apenas** de `contratos[0].razaoSocial`; pode não ser o titular.    |
| O que foi corrigido?             | Priorizar nome do titular no nível da resposta do SGP + logs de diagnóstico. |
