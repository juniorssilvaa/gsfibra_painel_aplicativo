#!/usr/bin/env python
"""
Script para enviar mensagem com chave PIX via WhatsApp Cloud API
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

from core.models import Provedor, Canal
from conversations.models import Conversation, Contact, Inbox
from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
import requests
import json

def send_pix_key():
    """Envia mensagem com chave PIX para o número especificado"""
    
    # Buscar provedor 1
    try:
        provedor = Provedor.objects.get(id=1)
    except Provedor.DoesNotExist:
        print("Erro: Provedor 1 não encontrado")
        return
    
    # Buscar canal WhatsApp Oficial do provedor
    canal = Canal.objects.filter(
        provedor=provedor,
        tipo="whatsapp_oficial",
        ativo=True
    ).first()
    
    if not canal:
        print("Erro: Canal WhatsApp Oficial não encontrado para o provedor 1")
        return
    
    if not canal.token:
        print("Erro: Token do canal não configurado")
        return
    
    if not canal.phone_number_id:
        print("Erro: Phone Number ID não configurado")
        return
    
    # Número de destino
    phone_number = "5563992484773"
    
    # Chave PIX
    pix_key = "d4f05f3a-4aef-434c-b604-a4f47e3e710d"
    
    # Normalizar número
    normalized_phone = ''.join(filter(str.isdigit, phone_number))
    
    # Preparar payload para mensagem interativa com botões
    import requests
    import json
    
    url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {canal.token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"💳 Chave PIX\n\nChave aleatória: {pix_key}\n\nUse o botão abaixo para copiar a chave."
            },
            "footer": {
                "text": "NIO CHAT"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "copy-pix-key",
                            "title": "📋 Copiar chave Pix"
                        }
                    }
                ]
            }
        }
    }
    
    print(f"Enviando mensagem PIX interativa para {phone_number}...")
    print(f"Canal: {canal.id}, Phone Number ID: {canal.phone_number_id}")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    # Enviar mensagem interativa
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    
    if response.status_code == 200:
        response_data = response.json()
        print(f"\n✅ Mensagem interativa enviada com sucesso!")
        print(f"Resposta: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
        
        # Salvar mensagem no banco
        contact, _ = Contact.objects.get_or_create(
            phone=normalized_phone,
            provedor=provedor,
            defaults={"name": normalized_phone}
        )
        
        inbox, _ = Inbox.objects.get_or_create(
            channel_type="whatsapp",
            provedor=provedor,
            defaults={
                "name": f"WhatsApp - {provedor.nome}",
                "channel_id": "whatsapp_cloud_api"
            }
        )
        
        conversation, _ = Conversation.objects.get_or_create(
            contact=contact,
            inbox=inbox,
            defaults={"status": "pending"}
        )
        
        from conversations.models import Message
        message_id = response_data.get("messages", [{}])[0].get("id")
        if message_id:
            Message.objects.create(
                conversation=conversation,
                content=f"💳 Chave PIX\n\nChave aleatória: {pix_key}",
                message_type="interactive",
                is_from_customer=False,
                external_id=message_id,
                additional_attributes={
                    "interactive_type": "button",
                    "pix_key": pix_key,
                    "source": "whatsapp_cloud_api"
                }
            )
            print(f"Mensagem salva no banco com ID externo: {message_id}")
    else:
        error_msg = response.text
        print(f"\n❌ Erro ao enviar mensagem interativa: HTTP {response.status_code}")
        print(f"Erro: {error_msg}")
        try:
            error_json = response.json()
            print(f"Detalhes: {json.dumps(error_json, indent=2, ensure_ascii=False)}")
        except:
            pass

if __name__ == "__main__":
    send_pix_key()

