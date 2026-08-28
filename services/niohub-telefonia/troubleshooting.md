# Guia de Solução de Problemas (Troubleshooting) - NIO HUB Telefonia

Este documento lista os erros mais comuns que podem ocorrer durante o desenvolvimento e execução do NIO HUB Telefonia, juntamente com suas soluções detalhadas.

## 1. Problema: "Consigo ouvir a pessoa, mas ela não me ouve"

**Sintoma:** A chamada conecta normalmente e você escuta o áudio do WhatsApp da outra pessoa no seu fone, mas quando você fala no microfone, a outra pessoa não escuta nada (fica mudo).

**Causa:**
Isso ocorre geralmente por falha na ponte de mídia (WebRTC -> Go Server -> WhatsApp Relay). Especificamente, quando o servidor Go perde a sincronia do fluxo RTP (pacotes de áudio) vindo do navegador, ou o decodificador Opus nativo fica em um estado travado aguardando amostras válidas.

**A Correção Feita:**
O que resolveu o seu caso foi um **reinício limpo da stack com a re-inicialização forçada do decoder Opus**. Quando reiniciamos o servidor Go com o ambiente CGO (`w64devkit`) recarregado do zero, as variáveis e ponteiros C da biblioteca `libopus_mlow` foram reconstruídas na memória. Além disso, a adição de logs no `OnBrowserRTP` (no arquivo `httpapi.go`) forçou a recompilação do binário, garantindo que a ponte WebRTC descartasse conexões residuais (fantasmas) e conectasse perfeitamente ao seu microfone desta vez.

**Como resolver caso ocorra novamente:**
1. Verifique se o navegador tem permissão para usar o microfone e se o dispositivo correto está selecionado no discador do app.
2. Atualize a página do navegador (F5).
3. Se persistir, reinicie o servidor Go fechando o terminal e rodando novamente o comando com CGO habilitado.

---

## 2. Erro 500 na tela de Login

**Sintoma:** Ao tentar colocar a URL (`http://localhost:5173`) e clicar em "Entrar", aparece um texto em vermelho "Erro 500".

**Causa:** 
O frontend (React/Vite) utiliza um *proxy* interno para redirecionar as chamadas de API (`/api/*`) para o backend Go. Se o arquivo `vite.config.ts` estiver apontando para uma porta errada (ex: `3001`), ele não encontra o servidor Go (que roda na porta `8080`) e lança um erro 500 de conexão recusada.

**Solução:**
Abra o arquivo `client/vite.config.ts` e altere a propriedade `target` do proxy para apontar para o Go:
```typescript
proxy: {
  "/api": { target: "http://localhost:8080", changeOrigin: true, ws: false },
}
```

---

## 3. Banco de dados corrompido ou erro "Connection Refused" na porta 5432

**Sintoma:** O servidor Go falha ao iniciar dizendo que a variável `WACALLS_PG_URL` está inválida ou que não consegue conectar no PostgreSQL. Ao verificar o log do postgres, há mensagens como `PÂNICO: não foi possível localizar registro do ponto de controle válido`.

**Causa:**
O Postgres portátil do Windows foi desligado incorretamente (queda de energia ou processo finalizado à força, como quando a IDE fecha tudo abruptamente), corrompendo os arquivos do catálogo (como o `pg_wal`).

**Solução:**
É necessário reinicializar o cluster de dados do banco portátil. No PowerShell, execute:
```powershell
# Apaga os dados corrompidos
Remove-Item -Recurse -Force ".\postgres\data"
New-Item -ItemType Directory -Path ".\postgres\data"

# Reinicializa o cluster limpo
.\postgres\pgsql\bin\initdb.exe -D ".\postgres\data" -U postgres -E UTF8 --locale=C

# Inicia o servidor novamente
.\postgres\pgsql\bin\pg_ctl.exe start -D ".\postgres\data" -l ".\postgres\postgres.log" -w
```
*(Lembre-se que recriar o cluster apagará o histórico das sessões locais anteriores)*.

---

## 4. O sistema inicia, conecta a chamada, mas fica TOTALMENTE mudo (os dois lados)

**Sintoma:** A chamada atende, o relógio corre, mas ninguém escuta nada.

**Causa:**
Você iniciou o servidor Go **sem o compilador CGO habilitado**. O NIO HUB Telefonia possui um fallback: se não compilar com o codec MLow nativo (escrito em C), ele roda em "modo sinalização", onde apenas troca mensagens de controle com o WhatsApp, mas ignora o tráfego de áudio bidirecional.

**Solução:**
Sempre inicie o servidor com as variáveis do `w64devkit` exportadas no Windows, apontando para as bibliotecas nativas:
```powershell
$env:CGO_ENABLED="1"
$env:CC="$PWD\w64devkit\bin\gcc.exe"
$env:CGO_LDFLAGS="-L$PWD/native -lopus_mlow"
$env:PATH="$PWD\w64devkit\bin;$PWD\native;" + $env:PATH
go run -tags mlow ./cmd/server -addr :8080 -debug
```
