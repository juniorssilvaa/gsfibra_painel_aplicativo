import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from core.models import Provedor, MensagemSistema
from conversations.models import Contact
from integrations.asaas_service import AsaasService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Processa faturas do Asaas e notifica provedores sobre cobranças vencidas ou pendentes'

    def handle(self, *args, **options):
        self.stdout.write("Iniciando processamento de faturas Asaas...")
        
        asaas = AsaasService()
        if not asaas.access_token:
            self.stderr.write(self.style.ERROR("ERRO: Token do Asaas não configurado."))
            return

        # 1. Buscar faturas VENCIDAS (OVERDUE)
        self.stdout.write("Buscando faturas vencidas...")
        overdue_res = asaas.list_payments(status="OVERDUE")
        
        # 2. Buscar faturas PENDENTES que vencem hoje
        today_str = datetime.now().strftime('%Y-%m-%d')
        self.stdout.write(f"Buscando faturas pendentes para hoje ({today_str})...")
        pending_res = asaas.list_payments(status="PENDING", due_date_le=today_str)

        all_payments = []
        if overdue_res.get("success"):
            all_payments.extend(overdue_res["data"])
        if pending_res.get("success"):
            all_payments.extend(pending_res["data"])

        if not all_payments:
            self.stdout.write(self.style.SUCCESS("Nenhuma fatura relevante encontrada."))
            return

        processed_count = 0
        for payment in all_payments:
            customer_id = payment.get("customer")
            value = payment.get("value")
            due_date = payment.get("dueDate")
            status = payment.get("status")
            invoice_id = payment.get("id")
            
            # Tentar encontrar o contato pelo asaas_customer_id nos additional_attributes
            contact = Contact.objects.filter(additional_attributes__asaas_customer_id=customer_id).first()
            
            if not contact or not contact.provedor:
                logger.warning(f"Pagamento {invoice_id} ignorado: Cliente Asaas {customer_id} não vinculado a nenhum contato/provedor no sistema.")
                continue

            # Criar notificação para o provedor
            status_label = "VENCIDA" if status == "OVERDUE" else "PENDENTE/VENCENDO"
            assunto = f"Fatura {status_label}: {contact.name}"
            mensagem = (
                f"O cliente {contact.name} possui uma fatura {status.lower()} no Asaas.\n"
                f"Valor: R$ {value}\n"
                f"Vencimento: {due_date}\n"
                f"ID Asaas: {invoice_id}"
            )

            # Evitar duplicidade de notificação para a mesma fatura no mesmo dia
            # (Poderíamos checar se já existe uma MensagemSistema com esse ID no conteúdo)
            exists = MensagemSistema.objects.filter(
                provedor=contact.provedor,
                assunto=assunto,
                ativa=True
            ).exists()

            if not exists:
                MensagemSistema.objects.create(
                    assunto=assunto,
                    mensagem=mensagem,
                    titulo=assunto,
                    conteudo=mensagem,
                    tipo='aviso',
                    provedor=contact.provedor,
                    visivel_para_agentes=False # Apenas Admins veem questões financeiras
                )
                processed_count += 1
                self.stdout.write(f"✓ Notificação criada para {contact.provedor.nome}: {assunto}")

        self.stdout.write(self.style.SUCCESS(f"Processamento concluído. {processed_count} notificações geradas."))
