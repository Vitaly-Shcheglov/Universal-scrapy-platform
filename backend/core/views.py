import os
from typing import Any, Dict, List, Optional, Tuple

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg, Q, F
from django.utils import timezone
from datetime import timedelta

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import (
    Category, Source, Product, PriceHistory, ParseRun, ParseError,
    Product as ProductModel
)
from .serializers import (
    CategorySerializer, SourceSerializer, ProductListSerializer,
    ProductDetailSerializer, PriceHistorySerializer, ParseRunSerializer,
    ParseErrorSerializer
)
from .filters import ProductFilter


class CategoryViewSet(viewsets.ModelViewSet):
    """API для работы с категориями"""
    queryset: models.QuerySet = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    filter_backends: List = [filters.SearchFilter, filters.OrderingFilter]
    search_fields: List[str] = ['name', 'slug']
    ordering_fields: List[str] = ['name', 'created_at']

    @action(detail=False, methods=['get'])
    def tree(self, request: Any) -> Response:
        """Получить дерево категорий"""
        root_categories: models.QuerySet = self.queryset.filter(parent=None)
        serializer = self.get_serializer(root_categories, many=True)
        return Response(serializer.data)


class SourceViewSet(viewsets.ModelViewSet):
    """API для работы с источниками"""
    queryset: models.QuerySet = Source.objects.all()
    serializer_class = SourceSerializer
    filter_backends: List = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields: List[str] = ['source_type', 'is_active']
    search_fields: List[str] = ['name', 'base_url']
    ordering_fields: List[str] = ['name', 'last_parse_at', 'created_at']

    @action(detail=True, methods=['post'])
    def parse(self, request: Any, pk: Optional[int] = None) -> Response:
        """Запустить парсинг источника"""
        source: Source = self.get_object()

        if not source.is_active:
            return Response(
                {'error': 'Источник неактивен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Импортируем здесь, чтобы избежать циклических импортов
        from parser.tasks import parse_source_task

        task = parse_source_task.delay(source.id)

        return Response({
            'message': 'Парсинг запущен',
            'task_id': task.id,
            'source': source.name
        })

    @action(detail=True, methods=['get'])
    def stats(self, request: Any, pk: Optional[int] = None) -> Response:
        """Статистика по источнику"""
        source: Source = self.get_object()

        products_count: int = source.products.count()
        active_products: int = source.products.filter(is_active=True).count()
        avg_price: Optional[float] = source.products.aggregate(Avg('price'))['price__avg']
        last_runs: models.QuerySet = source.parse_runs.all()[:5]

        return Response({
            'products_count': products_count,
            'active_products': active_products,
            'inactive_products': products_count - active_products,
            'average_price': float(avg_price) if avg_price else 0,
            'last_runs': ParseRunSerializer(last_runs, many=True).data
        })


class ProductViewSet(viewsets.ModelViewSet):
    """API для работы с товарами"""
    queryset: models.QuerySet = Product.objects.select_related('source', 'category').filter(is_active=True)
    filter_backends: Tuple = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = ProductFilter
    search_fields: Tuple[str, ...] = ('name', 'article', 'brand', 'description')
    ordering_fields: List[str] = ['price', 'rating', 'created_at', 'last_parse_at']

    def get_serializer_class(self) -> Any:
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=True, methods=['get'])
    def price_history(self, request: Any, pk: Optional[int] = None) -> Response:
        """История цен товара"""
        product: Product = self.get_object()
        days: int = int(request.query_params.get('days', 30))

        date_from: timezone.datetime = timezone.now() - timedelta(days=days)
        history: models.QuerySet = product.price_history.filter(recorded_at__gte=date_from)

        serializer = PriceHistorySerializer(history, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def price_drops(self, request: Any) -> Response:
        """Товары со снижением цены"""
        products: models.QuerySet = self.get_queryset().filter(
            old_price__isnull=False,
            old_price__gt=F('price')
        )

        page: Optional[models.QuerySet] = self.paginate_queryset(products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def out_of_stock(self, request: Any) -> Response:
        """Товары, которых нет в наличии"""
        products: models.QuerySet = self.get_queryset().filter(
            availability=Product.AvailabilityStatus.OUT_OF_STOCK
        )

        page: Optional[models.QuerySet] = self.paginate_queryset(products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)


class ParseRunViewSet(viewsets.ReadOnlyModelViewSet):
    """API для просмотра запусков парсинга"""
    queryset: models.QuerySet = ParseRun.objects.select_related('source').all()
    serializer_class = ParseRunSerializer
    filter_backends: List = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields: List[str] = ['source', 'status']
    ordering_fields: List[str] = ['created_at', 'finished_at', 'total_items']

    @action(detail=True, methods=['get'])
    def errors(self, request: Any, pk: Optional[int] = None) -> Response:
        """Ошибки конкретного запуска"""
        parse_run: ParseRun = self.get_object()
        errors: models.QuerySet = parse_run.errors.all()

        page: Optional[models.QuerySet] = self.paginate_queryset(errors)
        if page is not None:
            serializer = ParseErrorSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ParseErrorSerializer(errors, many=True)
        return Response(serializer.data)


class ParseErrorViewSet(viewsets.ReadOnlyModelViewSet):
    """API для просмотра ошибок парсинга"""
    queryset: models.QuerySet = ParseError.objects.select_related('parse_run', 'parse_run__source').all()
    serializer_class = ParseErrorSerializer
    filter_backends: List = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields: List[str] = ['parse_run', 'error_type']
    search_fields: List[str] = ['error_message', 'url']
    ordering_fields: List[str] = ['created_at']
