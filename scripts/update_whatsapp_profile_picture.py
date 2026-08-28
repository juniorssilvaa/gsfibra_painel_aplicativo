#!/usr/bin/env python
"""
Script para atualizar a foto do perfil do WhatsApp Business para canais já conectados
"""
import os
import sys
import django

# Configurar Django
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

from core.models import Canal, Provedor
from integrations.embedded_signup_finish import fetch_business_profile

def update_profile_picture(canal_id=None, provedor_id=None):
    """
    Atualiza a foto do perfil do WhatsApp Business para canais conectados.
    
    Args:
        canal_id: ID específico do canal (opcional)
        provedor_id: ID do provedor (opcional, atualiza todos os canais do provedor)
    """
    
    if canal_id:
        canais = Canal.objects.filter(id=canal_id, tipo="whatsapp_oficial", ativo=True)
    elif provedor_id:
        canais = Canal.objects.filter(provedor_id=provedor_id, tipo="whatsapp_oficial", ativo=True)
    else:
        canais = Canal.objects.filter(tipo="whatsapp_oficial", ativo=True)
    
    if not canais.exists():
        print("Nenhum canal WhatsApp Oficial encontrado.")
        return
    
    for canal in canais:
        print(f"\nProcessando canal ID {canal.id} - Provedor: {canal.provedor.nome if canal.provedor else 'N/A'}")
        
        if not canal.phone_number_id:
            print(f"  ⚠️  Canal {canal.id} não possui phone_number_id")
            continue
        
        if not canal.token:
            print(f"  ⚠️  Canal {canal.id} não possui token")
            continue
        
        print(f"  Buscando foto do perfil para phone_number_id: {canal.phone_number_id}")
        
        try:
            profile = fetch_business_profile(canal.phone_number_id, canal.token)
            
            if profile:
                profile_picture_url = profile.get("profile_picture_url")
                
                if profile_picture_url:
                    # Garantir que dados_extras existe
                    if not canal.dados_extras:
                        canal.dados_extras = {}
                    
                    # Salvar URL da foto do perfil nos dados extras (ambos os formatos para compatibilidade)
                    canal.dados_extras["profile_picture_url"] = profile_picture_url
                    canal.dados_extras["profilePicUrl"] = profile_picture_url
                    canal.dados_extras["business_about"] = profile.get("about")
                    canal.dados_extras["business_description"] = profile.get("description")
                    canal.dados_extras["business_address"] = profile.get("address")
                    canal.dados_extras["business_email"] = profile.get("email")
                    canal.dados_extras["business_vertical"] = profile.get("vertical")
                    canal.dados_extras["business_websites"] = profile.get("websites", [])
                    
                    # Salvar no banco
                    canal.save(update_fields=["dados_extras"])
                    
                    print(f"  ✅ Foto do perfil atualizada: {profile_picture_url[:60]}...")
                else:
                    print(f"  ⚠️  Perfil encontrado mas sem foto do perfil")
            else:
                print(f"  ❌ Não foi possível buscar o perfil")
                
        except Exception as e:
            print(f"  ❌ Erro ao buscar perfil: {str(e)}")
    
    print("\n✅ Processamento concluído!")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Atualizar foto do perfil do WhatsApp Business')
    parser.add_argument('--canal-id', type=int, help='ID específico do canal')
    parser.add_argument('--provedor-id', type=int, help='ID do provedor (atualiza todos os canais do provedor)')
    
    args = parser.parse_args()
    
    update_profile_picture(canal_id=args.canal_id, provedor_id=args.provedor_id)



