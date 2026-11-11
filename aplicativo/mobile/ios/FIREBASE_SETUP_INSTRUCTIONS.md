# Finalização da Configuração Firebase (iOS)

Para que as notificações push e outros recursos do Firebase funcionem no iOS:

1. Acesse o [Console do Firebase](https://console.firebase.google.com/).
2. Adicione um novo App ao seu projeto existente, selecionando a plataforma **iOS**.
3. Use o Bundle ID: `com.gsfibra.app`.
4. Baixe o arquivo `GoogleService-Info.plist`.
5. Coloque o arquivo na pasta: `mobile/ios/Runner/`.
6. **Importante:** No Xcode, clique com o botão direito na pasta `Runner` e selecione "Add Files to 'Runner'...", escolhendo o arquivo `GoogleService-Info.plist`.

### No Mac

```bash
cd ios
pod install
```
