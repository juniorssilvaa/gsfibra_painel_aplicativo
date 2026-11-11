"""
Product suggestions board (shared across all tenants).
"""
from __future__ import annotations

from django.db import models as dj_models
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from .models import Provedor, ProductSuggestion, ProductSuggestionVote, ProductSuggestionComment


def _auth_provedor_from_bearer(request):
    auth = (request.headers.get('Authorization') or '').strip()
    low = auth.lower()
    if not low.startswith('bearer '):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    return Provedor.objects.filter(integration_token=token).first()


class ProductSuggestionSerializer(serializers.ModelSerializer):
    provedor_nome = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    user_voted = serializers.SerializerMethodField()

    class Meta:
        model = ProductSuggestion
        fields = [
            'id',
            'provedor',
            'provedor_nome',
            'title',
            'description',
            'status',
            'status_label',
            'author_name',
            'created_by_name',
            'author_user_id',
            'votes_count',
            'comments_count',
            'user_voted',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'provedor',
            'votes_count',
            'comments_count',
            'author_name',
            'author_user_id',
            'created_at',
            'updated_at',
        ]

    def get_provedor_nome(self, obj):
        return obj.provedor.nome if obj.provedor_id else ''

    def get_status_label(self, obj):
        return obj.get_status_display()

    def get_created_by_name(self, obj):
        return obj.author_name or 'Usuario'

    def get_user_voted(self, obj):
        voted_ids = self.context.get('voted_ids')
        if voted_ids is not None:
            return obj.id in voted_ids
        return False


class ProductSuggestionViewSet(viewsets.ModelViewSet):
    """CRUD interno do superadmin (Token do usuario superadmin)."""
    serializer_class = ProductSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = ProductSuggestion.objects.select_related('provedor').all()
        status_filter = (self.request.query_params.get('status') or '').strip().lower()
        if status_filter in ('analise', 'desenvolvimento', 'concluido'):
            qs = qs.filter(status=status_filter)
        return qs.order_by('-votes_count', '-created_at')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['voted_ids'] = set()
        return ctx

    def partial_update(self, request, *args, **kwargs):
        user = request.user
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            return Response({'error': 'Forbidden'}, status=403)
        # Superadmin so altera status
        data = {}
        if 'status' in request.data:
            st = str(request.data.get('status') or '').strip().lower()
            if st not in ('analise', 'desenvolvimento', 'concluido'):
                return Response({'error': 'Status invalido'}, status=400)
            data['status'] = st
        if not data:
            return Response({'error': 'Nada para atualizar'}, status=400)
        instance = self.get_object()
        for k, v in data.items():
            setattr(instance, k, v)
        instance.save(update_fields=list(data.keys()) + ['updated_at'])
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['get'], url_path='comments')
    def comments(self, request, pk=None):
        """Lista comentarios para o superadmin (Token)."""
        user = request.user
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            return Response({'error': 'Forbidden'}, status=403)
        suggestion = self.get_object()
        qs = (
            ProductSuggestionComment.objects
            .filter(suggestion=suggestion)
            .select_related('author_provedor')
            .order_by('created_at')
        )
        return Response(ProductSuggestionCommentSerializer(qs, many=True).data)


class ProviderSuggestionsWebhookView(APIView):
    """
    Tenant (painel do provedor) lista/cria sugestões publicas.
    Auth: Authorization: Bearer <integration_token>
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        provedor = _auth_provedor_from_bearer(request)
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        qs = ProductSuggestion.objects.select_related('provedor').all()
        status_filter = (request.query_params.get('status') or '').strip().lower()
        if status_filter in ('analise', 'desenvolvimento', 'concluido'):
            qs = qs.filter(status=status_filter)
        qs = qs.order_by('-votes_count', '-created_at')

        voted_ids = set(
            ProductSuggestionVote.objects.filter(
                voter_provedor=provedor,
                voter_user_id=int(request.query_params.get('voter_user_id') or 0) or -1,
            ).values_list('suggestion_id', flat=True)
        ) if request.query_params.get('voter_user_id') else set()

        ser = ProductSuggestionSerializer(qs, many=True, context={'voted_ids': voted_ids})
        return Response(ser.data)

    def post(self, request):
        provedor = _auth_provedor_from_bearer(request)
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        title = (request.data.get('title') or '').strip()
        description = (request.data.get('description') or '').strip()
        if not title or not description:
            return Response({'error': 'Titulo e descricao sao obrigatorios'}, status=400)

        author_name = (request.data.get('author_name') or '').strip() or 'Usuario'
        author_user_id = request.data.get('author_user_id')
        try:
            author_user_id = int(author_user_id) if author_user_id is not None else None
        except Exception:
            author_user_id = None

        obj = ProductSuggestion.objects.create(
            provedor=provedor,
            title=title[:200],
            description=description,
            status='analise',
            author_name=author_name[:200],
            author_user_id=author_user_id,
        )
        return Response(
            ProductSuggestionSerializer(obj, context={'voted_ids': set()}).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderSuggestionVoteWebhookView(APIView):
    """POST vote toggle. Auth Bearer integration_token."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, pk):
        provedor = _auth_provedor_from_bearer(request)
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        try:
            suggestion = ProductSuggestion.objects.get(pk=pk)
        except ProductSuggestion.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        try:
            voter_user_id = int(request.data.get('voter_user_id') or 0)
        except Exception:
            voter_user_id = 0
        if voter_user_id <= 0:
            return Response({'error': 'voter_user_id obrigatorio'}, status=400)

        voter_name = (request.data.get('voter_name') or '').strip()[:200]
        existing = ProductSuggestionVote.objects.filter(
            suggestion=suggestion,
            voter_provedor=provedor,
            voter_user_id=voter_user_id,
        ).first()

        if existing:
            existing.delete()
            ProductSuggestion.objects.filter(id=suggestion.id, votes_count__gt=0).update(
                votes_count=dj_models.F('votes_count') - 1
            )
            voted = False
        else:
            ProductSuggestionVote.objects.create(
                suggestion=suggestion,
                voter_provedor=provedor,
                voter_user_id=voter_user_id,
                voter_name=voter_name,
            )
            ProductSuggestion.objects.filter(id=suggestion.id).update(
                votes_count=dj_models.F('votes_count') + 1
            )
            voted = True

        suggestion.refresh_from_db()
        return Response({
            'success': True,
            'voted': voted,
            'votes_count': suggestion.votes_count,
        })


class ProductSuggestionCommentSerializer(serializers.ModelSerializer):
    provedor_nome = serializers.SerializerMethodField()

    class Meta:
        model = ProductSuggestionComment
        fields = [
            'id',
            'suggestion',
            'author_name',
            'author_user_id',
            'provedor_nome',
            'body',
            'created_at',
        ]
        read_only_fields = fields

    def get_provedor_nome(self, obj):
        return obj.author_provedor.nome if obj.author_provedor_id else ''


class ProviderSuggestionCommentsWebhookView(APIView):
    """
    GET/POST comentarios publicos.
    Qualquer usuario autenticado via Bearer do provedor pode listar/comentar
    em qualquer sugestao (board compartilhado).
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, pk):
        provedor = _auth_provedor_from_bearer(request)
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)
        try:
            suggestion = ProductSuggestion.objects.get(pk=pk)
        except ProductSuggestion.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)
        qs = (
            ProductSuggestionComment.objects
            .filter(suggestion=suggestion)
            .select_related('author_provedor')
            .order_by('created_at')
        )
        return Response(ProductSuggestionCommentSerializer(qs, many=True).data)

    def post(self, request, pk):
        provedor = _auth_provedor_from_bearer(request)
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)
        try:
            suggestion = ProductSuggestion.objects.get(pk=pk)
        except ProductSuggestion.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'error': 'Comentario obrigatorio'}, status=400)
        if len(body) > 2000:
            return Response({'error': 'Comentario muito longo'}, status=400)

        try:
            author_user_id = int(request.data.get('author_user_id') or 0)
        except Exception:
            author_user_id = 0
        if author_user_id <= 0:
            return Response({'error': 'author_user_id obrigatorio'}, status=400)

        author_name = (request.data.get('author_name') or '').strip()[:200] or 'Usuario'

        comment = ProductSuggestionComment.objects.create(
            suggestion=suggestion,
            author_provedor=provedor,
            author_user_id=author_user_id,
            author_name=author_name,
            body=body,
        )
        ProductSuggestion.objects.filter(id=suggestion.id).update(
            comments_count=dj_models.F('comments_count') + 1
        )
        return Response(
            ProductSuggestionCommentSerializer(comment).data,
            status=status.HTTP_201_CREATED,
        )
