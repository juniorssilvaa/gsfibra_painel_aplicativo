"""Firebase Admin (push) — mesmo padrão do app_provedor."""
import os
import logging

logger = logging.getLogger(__name__)


def initialize_firebase():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning('[mobile_app] firebase-admin não instalado')
        return None

    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred_path = (os.environ.get('FIREBASE_CREDENTIALS') or '').strip()
    if cred_path and not os.path.exists(cred_path):
        logger.warning('[mobile_app] FIREBASE_CREDENTIALS não existe: %s', cred_path)
        cred_path = ''
    if not cred_path:
        from django.conf import settings
        base_dir = getattr(settings, 'BASE_DIR', None)
        candidates = [
            'firebase-credentials.json',
            'firebase_credentials.json',
            'service_account_key.json',
            '/opt/app_provedor/firebase-credentials.json',
            '/opt/app_provedor/firebase_credentials.json',
            '/opt/app_provedor/service_account_key.json',
        ]
        if base_dir:
            candidates.extend([
                str(base_dir / 'firebase-credentials.json'),
                str(base_dir / 'firebase_credentials.json'),
                str(base_dir / 'service_account_key.json'),
            ])
        for p in candidates:
            if os.path.exists(p):
                cred_path = p
                break

    if cred_path and os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            app = firebase_admin.initialize_app(cred)
            logger.info('[mobile_app] Firebase OK: %s', cred_path)
            return app
        except Exception as exc:
            logger.error('[mobile_app] Firebase init falhou: %s', exc)
            return None

    logger.warning('[mobile_app] Credenciais Firebase não encontradas')
    return None
