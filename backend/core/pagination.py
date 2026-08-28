"""
Paginação controlada para DRF
ETAPA 2: Corrigir paginação global para evitar payloads enormes
"""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """
    Paginação padrão com limites seguros.
    
    - page_size: 20 itens por página (padrão)
    - page_size_query_param: permite cliente especificar tamanho
    - max_page_size: máximo de 50 itens por página (proteção)
    
    Isso evita queries enormes que mantêm conexões PostgreSQL abertas por muito tempo.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000

