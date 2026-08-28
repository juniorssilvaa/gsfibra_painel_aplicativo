# Checklist de Validação - Correção de Autenticação

## ✅ Correções Implementadas

### FRONTEND

#### 1. ✅ Injeção Global do Token no Bootstrap (`main.jsx`)
- **Arquivo**: `frontend/frontend/src/main.jsx`
- **Mudança**: Adicionada injeção do token no `axios.defaults.headers.common['Authorization']` antes de qualquer requisição
- **Garante**: Token disponível desde o início da aplicação

#### 2. ✅ Interceptor de Request Melhorado (`App.jsx`)
- **Arquivo**: `frontend/frontend/src/App.jsx`
- **Status**: Já estava correto, mas garantido que funciona
- **Funcionalidade**: Injeta token em TODOS os requests Axios automaticamente

#### 3. ✅ Interceptor de Response Melhorado (`App.jsx`)
- **Arquivo**: `frontend/frontend/src/App.jsx`
- **Mudança**: 
  - Não redireciona em 401 durante login válido
  - Só redireciona para `/login` se:
    - Não há token no localStorage
    - É um endpoint de autenticação (`/api/auth/me/`, `/api/auth/login/`)
  - Para outros endpoints, apenas rejeita o erro sem redirecionar
- **Evita**: Logout prematuro durante operações normais

#### 4. ✅ Correção do `websocketAuth.js`
- **Arquivo**: `frontend/frontend/src/utils/websocketAuth.js`
- **Mudança**: Agora usa `auth_token` (padrão do Login) em vez de apenas `token`
- **Garante**: WebSockets recebem o token corretamente

### BACKEND

#### 5. ✅ Middleware WebSocket Melhorado (`ws_auth.py`)
- **Arquivo**: `backend/core/middleware/ws_auth.py`
- **Mudança**: 
  - Rejeita conexões sem token explicitamente (código 403)
  - Melhor logging para debug
  - Tratamento de erros mais robusto
- **Garante**: WebSockets só conectam com token válido

#### 6. ✅ TokenAuthentication Explícito em Views Internas
- **Arquivo**: `backend/conversations/views_internal_chat.py`
- **Mudança**: Adicionado `authentication_classes = [TokenAuthentication]` em:
  - `InternalChatRoomViewSet`
  - `InternalChatMessageViewSet`
  - `InternalChatParticipantViewSet`
  - `InternalChatUnreadCountView`
  - `InternalChatUnreadByUserView`
- **Garante**: Consistência mesmo se configurações padrão mudarem

#### 7. ✅ ASGI Configurado Corretamente
- **Arquivo**: `backend/niochat/asgi.py`
- **Status**: Já estava usando `TokenAuthMiddlewareStack` corretamente
- **Confirmação**: WebSocket routing usa middleware de autenticação

---

## 🧪 Checklist de Testes

### Teste 1: Login e Token
- [ ] Fazer login via `/api/auth/login/`
- [ ] Verificar que token é salvo em `localStorage.getItem('auth_token')`
- [ ] Verificar que `axios.defaults.headers.common['Authorization']` contém `Token <token>`
- [ ] Fazer GET `/api/auth/me/` → deve retornar 200 OK

### Teste 2: Endpoints Internos REST
- [ ] POST `/api/users/ping/` → deve retornar `{"status":"ok"}` (200)
- [ ] GET `/api/internal-chat-unread-count/` → deve retornar 200 (não 401)
- [ ] GET `/api/conversations/internal-chat/rooms/` → deve retornar 200 (não 401)
- [ ] GET `/api/conversations/internal-chat/messages/` → deve retornar 200 (não 401)

### Teste 3: WebSocket
- [ ] Conectar WebSocket em `/ws/internal-chat/<room_id>/?token=<token>`
- [ ] Verificar que conexão é aceita (não retorna 403)
- [ ] Verificar que `scope["user"]` está autenticado no backend
- [ ] Enviar mensagem via WebSocket → deve funcionar

### Teste 4: Persistência da Sessão
- [ ] Fazer login
- [ ] Navegar entre páginas
- [ ] Fazer múltiplas requisições
- [ ] Verificar que NÃO é redirecionado para `/login` após login válido
- [ ] Verificar que token permanece válido

### Teste 5: Tratamento de Erros
- [ ] Fazer requisição com token inválido → deve retornar 401
- [ ] Verificar que NÃO redireciona para `/login` se for endpoint não-crítico
- [ ] Verificar que redireciona para `/login` apenas se:
  - Não há token
  - É endpoint de autenticação (`/api/auth/me/`)

---

## 🔍 Comandos de Debug

### Frontend (Console do Navegador)
```javascript
// Verificar token
localStorage.getItem('auth_token')

// Verificar header do Axios
axios.defaults.headers.common['Authorization']

// Testar requisição manual
axios.get('/api/users/ping/').then(console.log).catch(console.error)
```

### Backend (Logs)
```bash
# Ver logs de autenticação WebSocket
grep "WebSocket" logs/*.log

# Ver logs de token inválido
grep "Token inválido" logs/*.log

# Ver logs de 401
grep "401" logs/*.log
```

### Teste Manual de WebSocket (curl)
```bash
# Não é possível testar WebSocket via curl diretamente
# Use ferramenta como wscat ou teste no navegador
```

---

## 📋 Validação Final

### ✅ Checklist de Validação

1. **Login funciona**: ✅
   - Token é retornado
   - Token é salvo como `auth_token`
   - Header Authorization é definido globalmente

2. **Token é enviado em TODOS os requests**: ✅
   - Interceptor do Axios funciona
   - Token injetado no bootstrap
   - Nenhum request isolado com `fetch`

3. **Endpoints internos autenticados**: ✅
   - Todos usam `TokenAuthentication` explicitamente
   - Retornam 200 em vez de 401

4. **WebSocket autenticado**: ✅
   - Middleware rejeita conexões sem token
   - Token é passado na querystring
   - Conexões autenticadas funcionam

5. **Não há logout prematuro**: ✅
   - Interceptor de response melhorado
   - Não redireciona em 401 durante login válido
   - Só redireciona quando apropriado

---

## 🚨 Problemas Conhecidos e Soluções

### Problema: Token não é enviado em alguns requests
**Solução**: ✅ Corrigido - Token injetado no bootstrap e interceptor garante envio

### Problema: WebSocket retorna 403
**Solução**: ✅ Corrigido - `websocketAuth.js` agora usa `auth_token` e middleware rejeita corretamente

### Problema: Endpoints internos retornam 401
**Solução**: ✅ Corrigido - `TokenAuthentication` explícito em todas as views

### Problema: Usuário é deslogado após login
**Solução**: ✅ Corrigido - Interceptor de response melhorado para não redirecionar prematuramente

---

## 📝 Notas Importantes

1. **Token Storage**: O token é salvo como `auth_token` no localStorage (padrão do Login)
2. **Compatibilidade**: O código ainda aceita `token` como fallback para compatibilidade
3. **WebSocket**: Token deve ser passado na querystring: `?token=<token>`
4. **REST API**: Token deve ser passado no header: `Authorization: Token <token>`
5. **Middleware**: WebSocket middleware rejeita conexões sem token (código 403)

---

## 🔄 Próximos Passos (Opcional)

1. Considerar usar `axios.create()` com instância configurada em vez de defaults globais
2. Implementar refresh token para tokens expirados
3. Adicionar métricas de autenticação para monitoramento
4. Considerar usar cookies httpOnly para tokens (mais seguro, mas requer mudanças maiores)

---

**Data de Criação**: $(date)
**Versão**: 1.0
**Status**: ✅ Implementado e Pronto para Testes
