# Contribuindo para o NioChat

Obrigado por seu interesse em contribuir para o NioChat! Este guia explica como contribuir para o projeto.

## Como Contribuir

### 1. Reportar Problemas
- Use o [GitHub Issues](https://github.com/juniorssilvaa/niochat/issues)
- Descreva o problema detalhadamente
- Inclua logs e screenshots se possível
- Use labels apropriadas

### 2. Sugerir Melhorias
- Use o [GitHub Discussions](https://github.com/juniorssilvaa/niochat/discussions)
- Descreva a melhoria proposta
- Explique o benefício para os usuários
- Considere a implementação

### 3. Enviar Pull Requests
- Fork o repositório
- Crie uma branch para sua feature
- Implemente as mudanças
- Teste suas mudanças
- Envie o pull request

## Processo de Desenvolvimento

### 1. Configurar Ambiente
```bash
# Fork e clone
git clone https://github.com/seu-usuario/niochat.git
cd niochat

# Configurar backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar frontend
cd ../frontend/frontend
npm install
```

### 2. Criar Branch
```bash
# Criar branch para feature
git checkout -b feature/nova-funcionalidade

# Criar branch para bugfix
git checkout -b bugfix/corrigir-problema
```

### 3. Implementar Mudanças
- Siga as convenções de código
- Escreva testes para novas funcionalidades
- Atualize a documentação se necessário
- Mantenha o código limpo e legível

### 4. Testar Mudanças
```bash
# Testes backend
cd backend
python manage.py test

# Testes frontend
cd frontend/frontend
npm test

# Lint
npm run lint
```

### 5. Enviar Pull Request
```bash
# Commit das mudanças
git add .
git commit -m "feat: adicionar nova funcionalidade"

# Push para seu fork
git push origin feature/nova-funcionalidade

# Criar pull request no GitHub
```

## Convenções de Código

### 1. Python (Backend)
```python
# Nomes de variáveis e funções
def process_message(message_text: str) -> str:
    """Processar mensagem com IA."""
    return ai_service.generate_response(message_text)

# Nomes de classes
class ConversationService:
    """Serviço para gerenciar conversas."""
    
    def create_conversation(self, contact_id: int) -> Conversation:
        """Criar nova conversa."""
        pass

# Nomes de constantes
MAX_MESSAGE_LENGTH = 1000
DEFAULT_TIMEOUT = 30
```

### 2. JavaScript (Frontend)
```javascript
// Nomes de variáveis e funções
const processMessage = (messageText) => {
  return aiService.generateResponse(messageText);
};

// Nomes de componentes
const ConversationList = ({ conversations }) => {
  return (
    <div className="conversation-list">
      {conversations.map(conversation => (
        <ConversationItem key={conversation.id} conversation={conversation} />
      ))}
    </div>
  );
};

// Nomes de constantes
const MAX_MESSAGE_LENGTH = 1000;
const DEFAULT_TIMEOUT = 30;
```

### 3. Commits
```bash
# Formato: tipo: descrição
feat: adicionar nova funcionalidade
fix: corrigir problema
docs: atualizar documentação
style: formatação de código
refactor: refatorar código
test: adicionar testes
chore: tarefas de manutenção
```

## Estrutura de Pull Request

### 1. Título
- Descreva claramente a mudança
- Use o formato: `tipo: descrição`
- Seja conciso mas descritivo

### 2. Descrição
```markdown
## Descrição
Descreva o que foi implementado ou corrigido.

## Tipo de Mudança
- [ ] Bug fix
- [ ] Nova funcionalidade
- [ ] Breaking change
- [ ] Documentação

## Como Testar
1. Passo 1
2. Passo 2
3. Passo 3

## Checklist
- [ ] Código testado
- [ ] Documentação atualizada
- [ ] Testes adicionados
- [ ] Lint passou
```

### 3. Checklist
- [ ] Código testado localmente
- [ ] Testes unitários passaram
- [ ] Lint passou
- [ ] Documentação atualizada
- [ ] Screenshots incluídas (se aplicável)

## Tipos de Contribuição

### 1. Bug Fixes
- Identifique o problema
- Crie um teste que reproduza o bug
- Implemente a correção
- Verifique que o teste passa
- Documente a correção

### 2. Novas Funcionalidades
- Discuta a funcionalidade primeiro
- Implemente com testes
- Atualize documentação
- Considere impacto na performance
- Mantenha compatibilidade

### 3. Melhorias de Performance
- Meça o impacto
- Documente as melhorias
- Mantenha funcionalidade
- Teste em diferentes cenários
- Considere trade-offs

### 4. Documentação
- Seja claro e conciso
- Use exemplos práticos
- Mantenha consistência
- Atualize regularmente
- Inclua screenshots

## Testes

### 1. Testes Unitários
```python
# backend/tests/test_models.py
class ConversationModelTest(TestCase):
    def test_create_conversation(self):
        """Testar criação de conversa."""
        contact = Contact.objects.create(name="Teste")
        conversation = Conversation.objects.create(contact=contact)
        self.assertEqual(conversation.status, 'open')
```

### 2. Testes de Integração
```python
# backend/tests/test_api.py
class ConversationAPITest(APITestCase):
    def test_list_conversations(self):
        """Testar listagem de conversas."""
        response = self.client.get('/api/conversations/')
        self.assertEqual(response.status_code, 200)
```

### 3. Testes Frontend
```javascript
// frontend/tests/ConversationList.test.jsx
import { render, screen } from '@testing-library/react';
import ConversationList from '../components/ConversationList';

test('renders conversation list', () => {
  const conversations = [
    { id: 1, name: 'Teste', status: 'open' }
  ];
  render(<ConversationList conversations={conversations} />);
  expect(screen.getByText('Teste')).toBeInTheDocument();
});
```

## Code Review

### 1. Como Revisar
- Verifique a funcionalidade
- Teste o código localmente
- Verifique testes
- Comente sugestões construtivas
- Aprove se estiver satisfeito

### 2. O que Procurar
- Funcionalidade correta
- Código limpo e legível
- Testes adequados
- Documentação atualizada
- Performance adequada
- Segurança

### 3. Comentários
- Seja construtivo
- Explique o porquê
- Sugira alternativas
- Reconheça boas práticas
- Seja respeitoso

## Comunidade

### 1. Código de Conduta
- Seja respeitoso
- Seja inclusivo
- Seja construtivo
- Seja paciente
- Seja colaborativo

### 2. Comunicação
- Use issues para problemas
- Use discussions para ideias
- Use pull requests para código
- Seja claro e direto
- Seja paciente com respostas

### 3. Suporte
- Leia a documentação primeiro
- Procure em issues existentes
- Seja específico no problema
- Inclua logs e screenshots
- Seja paciente

## Roadmap

### 1. Funcionalidades Planejadas
- [ ] Integração com Telegram
- [ ] Sistema de templates
- [ ] Analytics avançados
- [ ] API GraphQL
- [ ] Mobile app

### 2. Melhorias Técnicas
- [ ] Testes E2E
- [ ] CI/CD melhorado
- [ ] Monitoramento avançado
- [ ] Cache distribuído
- [ ] Microserviços

### 3. Documentação
- [ ] Tutoriais em vídeo
- [ ] Exemplos práticos
- [ ] Guias de deploy
- [ ] Troubleshooting
- [ ] FAQ

## Próximos Passos

1. [Estrutura](structure.md) - Entenda a estrutura do projeto
2. [Troubleshooting](troubleshooting.md) - Resolva problemas
3. [API](../api/endpoints.md) - Explore a API
4. [Configuração](../configuration/supabase.md) - Configure integrações

## Contato

- **GitHub**: [juniorssilvaa/niochat](https://github.com/juniorssilvaa/niochat)
- **Email**: suporte@niohub.com.br
- **Discord**: [Link do servidor](https://discord.gg/niochat)
- **Twitter**: [@niochat](https://twitter.com/niochat)

Obrigado por contribuir para o NioChat! 🚀
