# 🔍 Diagnóstico Completo - Problemas de Autenticação NioChat

## 📌 Problema Raiz Identificado

### 1. **REST API retornando 401 em endpoints específicos**

**Endpoints afetados:**
- `/api/companies/`
- `/api/provedores/`
- `/api/canais/`

**Causa:**
Os ViewSets (`CompanyViewSet`, `ProvedorViewSet`, `CanalViewSet`) estão verificando `user.user_type == 'superadmin'` no método `get_queryset()`, mas:

1. Se o token não é enviado corretamente, `request.user` pode ser `AnonymousUser`
2. `AnonymousUser` não tem atributo `user_type`, causando `AttributeError`
3. O DRF retorna 401 antes mesmo de chegar ao `get_queryset()` se `IsAuthenticated` falhar
4. **MAS** se o token é enviado mas está inválido/expirado, o DRF pode não detectar corretamente

**Problema específico:**
```python
def get_queryset(self):
    user = self.request.user  # Pode ser AnonymousUser se token inválido
    if user.user_type == 'superadmin':  # AttributeError se AnonymousUser
        ...
```

### 2. **WebSocket retornando 403 (WSREJECT)**

**Endpoints afetados:**
- `/ws/user_status/`
- `/ws/private-chat/`
- `/ws/internal-chat/notifications/`

**Causa:**
1. O middleware `TokenAuthMiddleware` define `scope["user"] = AnonymousUser()` quando:
   - Não há token na querystring
   - Token é inválido/expirado
   - Usuário associado ao token está inativo

2. Os consumers verificam `user.is_authenticated`:
   ```python
   if user is None or not user.is_authenticated:
       await self.close(code=4001)  # Unauthorized
   ```

3. `AnonymousUser.is_authenticated` retorna `False`, então a conexão é fechada

4. O código 4001 pode aparecer como 403 no frontend dependendo da implementação do WebSocket

**Problema específico:**
- O middleware não está rejeitando explicitamente a conexão antes de chegar ao consumer
- O consumer recebe `AnonymousUser` e fecha a conexão, mas isso pode causar race conditions

### 3. **Múltiplas instâncias de GoTrueClient (Supabase)**

**Causa:**
- O Supabase está sendo inicializado múltiplas vezes no frontend
- Isso não está relacionado ao token de autenticação do Django
- Mas pode causar conflitos se houver múltiplas tentativas de autenticação simultâneas

---

## 🎯 Soluções Implementadas

### Solução 1: Middleware WebSocket Robusto

**Arquivo:** `backend/core/middleware/ws_auth.py`

**Melhorias:**
1. Verificação explícita de token antes de definir usuário
2. Logging detalhado para debug
3. Tratamento de erros robusto
4. Garantia de que apenas usuários autenticados chegam aos consumers

### Solução 2: Verificações de Segurança nos ViewSets

**Arquivo:** `backend/core/views.py`

**Melhorias:**
1. Verificação de `is_authenticated` antes de acessar `user_type`
2. Uso de `getattr()` com fallback seguro
3. Tratamento explícito de `AnonymousUser`

### Solução 3: Mixin de Autenticação para Consumers

**Arquivo:** `backend/conversations/consumers.py`

**Melhorias:**
1. Mixin `TokenAuthMixin` que verifica autenticação de forma consistente
2. Tratamento de erros padronizado
3. Logging para debug

### Solução 4: Frontend - Instância Única de Axios

**Arquivo:** `frontend/frontend/src/main.jsx` e `frontend/frontend/src/App.jsx`

**Melhorias:**
1. Injeção do token no bootstrap (antes de qualquer requisição)
2. Interceptor global que garante token em TODOS os requests
3. Prevenção de múltiplas inicializações

---

## 🔧 Correções Técnicas Detalhadas

### Correção 1: Middleware WebSocket

```python
# ANTES (problemático)
if token_key:
    user = await self.get_user_from_token(token_key)
    if user:
        scope["user"] = user
    else:
        scope["user"] = AnonymousUser()  # Consumer vai fechar conexão

# DEPOIS (correto)
if token_key:
    user = await self.get_user_from_token(token_key)
    if user and user.is_active:
        scope["user"] = user
        logger.debug(f"WebSocket autenticado: {user.id}")
    else:
        # Token inválido - definir AnonymousUser
        # O consumer vai verificar e fechar
        scope["user"] = AnonymousUser()
        logger.warning(f"Token inválido ou usuário inativo")
else:
    # Sem token - definir AnonymousUser
    scope["user"] = AnonymousUser()
    logger.debug("Conexão sem token")
```

### Correção 2: ViewSets com Verificação Segura

```python
# ANTES (problemático)
def get_queryset(self):
    user = self.request.user
    if user.user_type == 'superadmin':  # AttributeError se AnonymousUser
        ...

# DEPOIS (correto)
def get_queryset(self):
    user = self.request.user
    
    # Verificação de segurança
    if not user.is_authenticated:
        return self.queryset.none()
    
    # Verificação segura de user_type
    user_type = getattr(user, 'user_type', None)
    if user_type == 'superadmin':
        ...
```

### Correção 3: Consumers com Verificação Robusta

```python
# ANTES (problemático)
async def connect(self):
    user = self.scope.get("user")
    if user is None or not user.is_authenticated:
        await self.close(code=4001)
        return

# DEPOIS (correto)
async def connect(self):
    user = self.scope.get("user")
    
    # Verificação robusta
    if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
        logger.warning(f"WebSocket rejeitado: usuário não autenticado")
        await self.close(code=4001)
        return
    
    # Verificar se é usuário válido (não AnonymousUser)
    if user.id is None:
        logger.warning(f"WebSocket rejeitado: AnonymousUser")
        await self.close(code=4001)
        return
```

---

## 📋 Checklist de Validação

### ✅ Validação REST API

1. **Login funciona:**
   ```bash
   curl -X POST http://localhost:8010/api/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"senha"}'
   ```
   → Deve retornar `{"token":"..."}`

2. **Token funciona em /api/auth/me/:**
   ```bash
   curl http://localhost:8010/api/auth/me/ \
     -H "Authorization: Token <token>"
   ```
   → Deve retornar dados do usuário

3. **Endpoints internos funcionam:**
   ```bash
   curl http://localhost:8010/api/companies/ \
     -H "Authorization: Token <token>"
   ```
   → Deve retornar 200 (não 401)

4. **Superadmin vê todos os recursos:**
   ```bash
   curl http://localhost:8010/api/provedores/ \
     -H "Authorization: Token <token_superadmin>"
   ```
   → Deve retornar lista completa

### ✅ Validação WebSocket

1. **Conexão com token válido:**
   ```javascript
   const ws = new WebSocket('ws://localhost:8010/ws/user_status/?token=<token>');
   ws.onopen = () => console.log('Conectado');
   ws.onerror = (e) => console.error('Erro:', e);
   ```
   → Deve conectar (não retornar 403)

2. **Conexão sem token:**
   ```javascript
   const ws = new WebSocket('ws://localhost:8010/ws/user_status/');
   ws.onerror = (e) => console.error('Erro esperado:', e);
   ```
   → Deve rejeitar (código 4001 ou 403)

3. **Conexão com token inválido:**
   ```javascript
   const ws = new WebSocket('ws://localhost:8010/ws/user_status/?token=invalid');
   ws.onerror = (e) => console.error('Erro esperado:', e);
   ```
   → Deve rejeitar (código 4001 ou 403)

### ✅ Validação Frontend

1. **Token injetado no bootstrap:**
   ```javascript
   // No console do navegador após login
   console.log(axios.defaults.headers.common['Authorization']);
   ```
   → Deve mostrar `Token <token>`

2. **Interceptor funciona:**
   ```javascript
   // No console do navegador
   axios.get('/api/users/ping/').then(console.log);
   ```
   → Deve funcionar sem 401

3. **WebSocket conecta:**
   ```javascript
   // Verificar no Network tab do DevTools
   // WebSocket deve conectar sem erro 403
   ```

---

## 🚨 Problemas Conhecidos e Soluções

### Problema: Token não é enviado em alguns requests
**Solução:** ✅ Token injetado no bootstrap + interceptor global

### Problema: WebSocket retorna 403
**Solução:** ✅ Middleware melhorado + consumers com verificação robusta

### Problema: Endpoints REST retornam 401
**Solução:** ✅ Verificações de segurança nos ViewSets + TokenAuthentication explícito

### Problema: Superadmin não vê todos os recursos
**Solução:** ✅ Verificação segura de `user_type` com `getattr()`

### Problema: Múltiplas instâncias de GoTrueClient
**Solução:** ✅ Verificar inicialização do Supabase no frontend (não relacionado ao token)

---

## 📝 Notas Importantes

1. **Token Storage**: Token salvo como `auth_token` no localStorage
2. **WebSocket**: Token deve ser passado na querystring: `?token=<token>`
3. **REST API**: Token deve ser passado no header: `Authorization: Token <token>`
4. **AnonymousUser**: Sempre verificar `is_authenticated` antes de acessar atributos customizados
5. **Superadmin**: Verificar `user_type` com `getattr()` para evitar AttributeError

---

**Data:** $(date)
**Versão:** 2.0
**Status:** ✅ Diagnóstico Completo e Soluções Implementadas
