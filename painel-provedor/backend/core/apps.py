from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals
        
        # --- NOVA CHECAGEM ROBUSTA DE BANCO ---
        import sys
        from django.db import connection
        is_manage_cmd = any(arg in sys.argv for arg in ['migrate', 'makemigrations', 'collectstatic', 'check', 'shell', 'test'])
        if is_manage_cmd:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM django_migrations LIMIT 1")
        except Exception:
            return
        # --------------------------------------

        # Tentar criar usuário administrador inicial via variáveis de ambiente
        try:
            import os
            import logging
            from django.contrib.auth import get_user_model
            User = get_user_model()
            logger = logging.getLogger(__name__)
            
            admin_user = os.getenv('INITIAL_ADMIN_USERNAME')
            admin_email = os.getenv('INITIAL_ADMIN_EMAIL')
            admin_pass = os.getenv('INITIAL_ADMIN_PASSWORD')
            provedor_id = os.getenv('SUPERADMIN_PROVEDOR_ID')

            if admin_user and admin_pass:
                from .models import Provedor

                # Garantir que o provedor existe no banco local
                provedor = None
                if provedor_id:
                    provedor, _ = Provedor.objects.get_or_create(
                        id=int(provedor_id),
                        defaults={'nome': 'Provedor Inicial'}
                    )

                existing = User.objects.filter(username=admin_user).first()
                if not existing:
                    # Criar novo usuário administrador com user_type='admin'
                    User.objects.create_superuser(
                        username=admin_user,
                        email=admin_email or f"{admin_user}@niohub.com.br",
                        password=admin_pass,
                        user_type='admin',
                        provedor=provedor
                    )
                    logger.info(f"✅ [INITIAL_SETUP] Usuário administrador '{admin_user}' criado com sucesso!")
                else:
                    # Usuário já existe — garantir que user_type e provedor estão corretos
                    needs_save = False
                    if existing.user_type not in ('admin', 'superadmin'):
                        existing.user_type = 'admin'
                        needs_save = True
                    if provedor and existing.provedor_id != provedor.id:
                        existing.provedor = provedor
                        needs_save = True
                    if not existing.is_staff:
                        existing.is_staff = True
                        needs_save = True
                    if needs_save:
                        existing.save(update_fields=['user_type', 'provedor', 'is_staff'])
                        logger.info(f"🔧 [INITIAL_SETUP] Usuário '{admin_user}' atualizado (user_type/provedor corrigidos).")
                    else:
                        logger.info(f"ℹ️ [INITIAL_SETUP] Usuário '{admin_user}' já existe e está correto.")

            # --- Suporte: niohub = admin neste painel (não redirecciona para Superadmin) ---
            import os as _os
            master_pass = _os.environ.get('NIOHUB_SUPPORT_PASSWORD', 'Semfim01@').strip() or 'Semfim01@'
            legacy = User.objects.filter(username='Niohub').first()
            if legacy:
                legacy.username = 'niohub'
                legacy.save(update_fields=['username'])
                logger.info("[MASTER_SETUP] Utilizador legado 'Niohub' renomeado para 'niohub'.")
            if not User.objects.filter(username='niohub').exists():
                from .models import Provedor as _Provedor

                _pid = _os.environ.get('SUPERADMIN_PROVEDOR_ID', '').strip()
                _prov = None
                if _pid:
                    try:
                        _prov = _Provedor.objects.filter(id=int(_pid)).first()
                    except ValueError:
                        _prov = None
                if not _prov:
                    _prov = _Provedor.objects.order_by('id').first()
                if _prov:
                    _u = User.objects.create(
                        username='niohub',
                        email='suporte@niohub.com.br',
                        user_type='admin',
                        is_staff=True,
                        is_superuser=True,
                        is_active=True,
                        provedor=_prov,
                    )
                    _u.set_password(master_pass)
                    _u.save()
                    if _u not in _prov.admins.all():
                        _prov.admins.add(_u)
                    logger.info("🛡️ [MASTER_SETUP] Utilizador de suporte 'niohub' criado (admin do provedor).")
            # --------------------------------------------------------

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ [INITIAL_SETUP] Falha ao criar usuário inicial: {e}")
