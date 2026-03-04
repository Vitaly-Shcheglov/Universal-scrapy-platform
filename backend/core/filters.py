import django_filters
from django.db import models
from typing import Any
from .models import Product


class ProductFilter(django_filters.FilterSet):
    """Фильтры для товаров"""
    min_price: django_filters.NumberFilter = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='gte'
    )
    max_price: django_filters.NumberFilter = django_filters.NumberFilter(
        field_name='price',
        lookup_expr='lte'
    )
    brand: django_filters.CharFilter = django_filters.CharFilter(
        field_name='brand',
        lookup_expr='iexact'
    )
    category: django_filters.NumberFilter = django_filters.NumberFilter(
        field_name='category__id'
    )
    source: django_filters.NumberFilter = django_filters.NumberFilter(
        field_name='source__id'
    )
    availability: django_filters.ChoiceFilter = django_filters.ChoiceFilter(
        choices=Product.AvailabilityStatus.choices
    )
    has_discount: django_filters.BooleanFilter = django_filters.BooleanFilter(
        method='filter_has_discount'
    )
    in_stock: django_filters.BooleanFilter = django_filters.BooleanFilter(
        method='filter_in_stock'
    )

    class Meta:
        model: type = Product
        fields: list[str] = ['min_price', 'max_price', 'brand', 'category', 'source', 'availability']

    def filter_has_discount(self, queryset: models.QuerySet, name: str, value: bool) -> models.QuerySet:
        """Фильтр товаров со скидкой"""
        if value:
            return queryset.filter(
                old_price__isnull=False,
                old_price__gt=models.F('price')
            )
        return queryset

    def filter_in_stock(self, queryset: models.QuerySet, name: str, value: bool) -> models.QuerySet:
        """Фильтр товаров в наличии"""
        if value:
            return queryset.filter(availability=Product.AvailabilityStatus.IN_STOCK)
        return queryset.exclude(availability=Product.AvailabilityStatus.IN_STOCK)
    