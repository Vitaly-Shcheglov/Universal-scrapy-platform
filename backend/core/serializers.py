from rest_framework import serializers
from typing import Any, Dict, List
from .models import Category, Source, Product, PriceHistory, ParseRun, ParseError


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор категорий с вложенными дочерними категориями"""
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields: List[str] = ['id', 'name', 'slug', 'parent', 'children', 'is_active', 'created_at', 'updated_at']
        read_only_fields: List[str] = ['created_at', 'updated_at']

    def get_children(self, obj) -> List[Dict[str, Any]] | List:
        """Получить активные дочерние категории"""
        if obj.children.exists():
            return CategorySerializer(obj.children.filter(is_active=True), many=True).data
        return []


class SourceSerializer(serializers.ModelSerializer):
    """Сериализатор источников с количеством товаров и статусом последнего парсинга"""
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    last_parse_status = serializers.SerializerMethodField()

    class Meta:
        model = Source
        fields: List[str] = [
            'id', 'name', 'source_type', 'base_url', 'is_active',
            'parse_interval', 'last_parse_at', 'config', 'headers',
            'products_count', 'last_parse_status', 'created_at', 'updated_at'
        ]
        read_only_fields: List[str] = ['created_at', 'updated_at', 'last_parse_at']

    def get_last_parse_status(self, obj)-> Dict[str, Any] | None:
        """Получить статус последнего запуска парсинга"""
        last_run = obj.parse_runs.first()
        if last_run:
            return {
                'status': last_run.status,
                'finished_at': last_run.finished_at,
                'total_items': last_run.total_items,
                'new_items': last_run.new_items,
                'updated_items': last_run.updated_items,
            }
        return None


class ProductListSerializer(serializers.ModelSerializer):
    """Сериализатор списка товаров для таблиц"""
    source_name = serializers.CharField(source='source.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    discount_percent = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields: List[str] = [
            'id', 'external_id', 'name', 'slug', 'article', 'brand',
            'price', 'old_price', 'currency', 'discount_percent',
            'availability', 'image_url', 'url', 'rating', 'reviews_count',
            'source_name', 'category_name', 'is_active', 'last_parsed_at'
        ]

    def get_discount_percent(self, obj) -> float:
        """Рассчитать процент скидки"""
        if obj.old_price and obj.old_price > obj.price:
            return round((1 - float(obj.price) / float(obj.old_price)) * 100, 2)
        return 0


class ProductDetailSerializer(serializers.ModelSerializer):
    """Полный сериализатор товара с историей цен"""
    source = SourceSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    price_changes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields: str = '__all__'

    def get_price_changes(self, obj) -> List[Dict[str, Any]]:
        """Получить последние 10 изменений цены"""
        history = obj.price_history.all()[:10]
        return PriceHistorySerializer(history, many=True).data


class PriceHistorySerializer(serializers.ModelSerializer):
    """Сериализатор истории цен"""
    price_change = serializers.SerializerMethodField()


class Meta:
    model = PriceHistory
    fields: List[str] = ['id', 'price', 'old_price', 'availability', 'recorded_at', 'price_change']


def get_price_change(self, obj) -> float:
    """Рассчитать изменение цены"""
    if obj.old_price and obj.old_price != obj.price:
        return float(obj.price - obj.old_price)
    return 0


class ParseRunSerializer(serializers.ModelSerializer):
    """Сериализатор запусков парсинга"""
    source_name = serializers.CharField(source='source.name', read_only=True)
    duration = serializers.IntegerField(read_only=True)
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = ParseRun
        fields: List[str] = [
            'id', 'source', 'source_name', 'status', 'started_at', 'finished_at',
            'duration', 'total_items', 'new_items', 'updated_items', 'failed_items',
            'success_rate', 'log', 'error_message', 'created_at'
        ]
        read_only_fields: List[str] = ['created_at']

    def get_success_rate(self, obj) -> float:
        """Рассчитать процент успешных парсингов"""
        if obj.total_items > 0:
            return round((obj.total_items - obj.failed_items) / obj.total_items * 100, 2)
        return 0


class ParseErrorSerializer(serializers.ModelSerializer):
    """Сериализатор ошибок парсинга"""
    class Meta:
        model = ParseError
        fields: List[str] = ['id', 'parse_run', 'url', 'error_type', 'error_message', 'traceback', 'data', 'created_at']
        read_only_fields: List[str] = ['created_at']
