from __future__ import annotations

from typing import Any, Optional

from django.contrib import admin
from django.db.models import Model
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from .models import Category, Source, Product, PriceHistory, ParseRun, ParseError


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Админка категорий: базовые поля, фильтры и количество товаров."""
    list_display = ['name', 'slug', 'parent', 'is_active', 'products_count', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

    def products_count(self, obj: Category) -> int:
        """Возвращает количество товаров в категории."""
        return obj.products.count()

    products_count.short_description = 'Товаров'


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    """Админка источников: настройки парсинга, метаданные и быстрый запуск."""
    list_display = ['name', 'source_type', 'is_active', 'products_count', 'last_parse_at', 'parse_action']
    list_filter = ['source_type', 'is_active']
    search_fields = ['name', 'base_url']
    readonly_fields = ['last_parse_at', 'created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'source_type', 'base_url', 'is_active', 'parse_interval')
        }),
        ('Настройки парсинга', {
            'fields': ('config', 'headers'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('last_parse_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def products_count(self, obj: Source) -> str:
        """Ссылка на список товаров источника с количеством."""
        count: int = obj.products.count()
        url: str = reverse('admin:core_product_changelist') + f'?source__id__exact={obj.id}'
        return format_html('<a href="{}">{}</a>', url, count)

    products_count.short_description = 'Товаров'

    def parse_action(self, obj: Source) -> str:
        """Кнопка для запуска парсинга источника (если активен)."""
        if obj.is_active:
            return format_html(
                '<a class="button" href="/api/sources/{}/parse/" target="_blank">Запустить парсинг</a>',
                obj.id,
            )
        return '-'

    parse_action.short_description = 'Действия'


class PriceHistoryInline(admin.TabularInline):
    """Инлайн последних записей истории цен (только чтение)."""
    model = PriceHistory
    extra = 0
    readonly_fields = ['price', 'old_price', 'availability', 'recorded_at']
    can_delete = False
    max_num = 10

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = None) -> bool:
        """Запрещает добавление записей вручную из админки."""
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Админка товаров: цена/наличие, медиа, метаданные парсинга и история цен."""
    list_display = [
        'name', 'article', 'brand', 'price_display', 'availability',
        'source', 'category', 'is_active', 'last_parsed_at'
    ]
    list_filter = ['availability', 'is_active', 'source', 'brand', 'category']
    search_fields = ['name', 'article', 'brand', 'external_id']
    readonly_fields = ['external_id', 'parse_count', 'last_parsed_at', 'created_at', 'updated_at', 'image_preview']
    inlines = [PriceHistoryInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('source', 'external_id', 'name', 'slug', 'article', 'brand', 'category')
        }),
        ('Цена и наличие', {
            'fields': ('price', 'old_price', 'currency', 'availability', 'stock_quantity')
        }),
        ('Описание', {
            'fields': ('short_description', 'description', 'specifications'),
            'classes': ('collapse',)
        }),
        ('Медиа', {
            'fields': ('image_url', 'image_preview', 'images'),
            'classes': ('collapse',)
        }),
        ('Дополнительно', {
            'fields': ('url', 'rating', 'reviews_count', 'is_active'),
        }),
        ('Метаданные', {
            'fields': ('parse_count', 'last_parsed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def price_display(self, obj: Product) -> str:
        """Красивое отображение цены и скидки (если есть old_price)."""
        if obj.old_price and obj.old_price > obj.price:
            discount: int = round((1 - float(obj.price) / float(obj.old_price)) * 100)
            return format_html(
                '<span style="color: red; font-weight: bold;">{} {}</span> '
                '<span style="text-decoration: line-through;">{}</span> '
                '<span style="color: green;">(-{}%)</span>',
                obj.price, obj.currency, obj.old_price, discount
            )
        return f"{obj.price} {obj.currency}"

    price_display.short_description = 'Цена'

    def image_preview(self, obj: Product) -> str:
        """Превью главного изображения по image_url."""
        if obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.image_url,
            )
        return '-'

    image_preview.short_description = 'Превью'


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    """Админка истории цен (только просмотр)."""
    list_display = ['product', 'price', 'old_price', 'availability', 'recorded_at']
    list_filter = ['availability', 'recorded_at']
    search_fields = ['product__name', 'product__article']
    readonly_fields = ['product', 'price', 'old_price', 'availability', 'recorded_at']
    date_hierarchy = 'recorded_at'

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Запрещает ручное добавление записей истории."""
        return False


class ParseErrorInline(admin.TabularInline):
    """Инлайн ошибок парсинга в рамках запуска (только чтение)."""
    model = ParseError
    extra = 0
    readonly_fields = ['url', 'error_type', 'error_message', 'created_at']
    can_delete = False
    max_num = 20

    def has_add_permission(self, request: HttpRequest, obj: Optional[Model] = None) -> bool:
        """Запрещает добавление ошибок вручную."""
        return False


@admin.register(ParseRun)
class ParseRunAdmin(admin.ModelAdmin):
    """Админка запусков парсинга: статус, статистика, логи и ошибки."""
    list_display = [
        'id', 'source', 'status_display', 'started_at', 'finished_at',
        'duration_display', 'total_items', 'new_items', 'updated_items', 'failed_items'
    ]
    list_filter = ['status', 'source', 'created_at']
    search_fields = ['id', 'source__name']
    readonly_fields = [
        'id', 'source', 'status', 'started_at', 'finished_at', 'duration_display',
        'total_items', 'new_items', 'updated_items', 'failed_items',
        'log', 'error_message', 'error_traceback', 'created_at', 'updated_at'
    ]
    inlines = [ParseErrorInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'source', 'status', 'started_at', 'finished_at', 'duration_display')
        }),
        ('Статистика', {
            'fields': ('total_items', 'new_items', 'updated_items', 'failed_items')
        }),
        ('Логи', {
            'fields': ('log', 'error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Запрещает создавать ParseRun вручную из админки."""
        return False

    def status_display(self, obj: ParseRun) -> str:
        """Цветная индикация статуса запуска."""
        colors: dict[str, str] = {
            'pending': 'gray',
            'running': 'blue',
            'success': 'green',
            'failed': 'red',
            'partial': 'orange',
        }
        color: str = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )

    status_display.short_description = 'Статус'

    def duration_display(self, obj: ParseRun) -> str:
        """Длительность запуска в секундах (если рассчитана)."""
        if obj.duration:
            return f"{obj.duration:.2f} сек"
        return '-'

    duration_display.short_description = 'Длительность'


@admin.register(ParseError)
class ParseErrorAdmin(admin.ModelAdmin):
    """Админка ошибок парсинга (только просмотр)."""
    list_display = ['parse_run', 'error_type', 'url', 'created_at']
    list_filter = ['error_type', 'created_at']
    search_fields = ['error_message', 'url']
    readonly_fields = ['parse_run', 'url', 'error_type', 'error_message', 'traceback', 'data', 'created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Запрещает добавление ошибок вручную."""
        return False
