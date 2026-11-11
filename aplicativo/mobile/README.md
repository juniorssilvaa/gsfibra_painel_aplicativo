# gsfibra Mobile App

Aplicativo de autoatendimento em Flutter para clientes gsfibra.

## Identidade

- Nome: `gsfibra`
- Flavor Android: `gsfibra`
- Application ID / Bundle ID: `com.gsfibra.app`
- Pacote Dart: `gsfibra`
- Firebase Android: `android/app/src/gsfibra/google-services.json`

## API

- Produção: `https://api.niohub.com.br/v1/` (ou a URL configurada no painel)

## Rodar

```bash
flutter run --flavor gsfibra

# APK
flutter build apk --flavor gsfibra --release

# AAB
flutter build appbundle --flavor gsfibra --release

# iOS
flutter build ios --release
```

## Observação Firebase / lojas

O bundle/package mudou para `com.gsfibra.app`. É preciso cadastrar esse ID no Firebase e gerar novos `google-services.json` / `GoogleService-Info.plist`, além do perfil de provisioning iOS `gsfibra_distribution` e do app no Google Play / App Store.
