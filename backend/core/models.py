from django.db import models
from django.core.validators import URLValidator, MinValueValidator
from django.utils import timezone
import uuid
from typing import Dict, List, Any


class TimeStampedModel(models.Model):
    """Абстрактная модель с временными метками"""
    createdat = models.DateTimeField('Создано', autonowadd=True)
    updatedat = models.DateTimeField('Обновлено', autonow=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    """Категория товаров"""
    name = models.CharField('Название', maxlength=255, unique=True)
    slug = models.SlugField('Slug', unique=True)
    parent = models.ForeignKey(
        'self',
        ondelete=models.CASCADE,
        null=True,
        blank=True,
        relatedname='children',
        verbosename='Родительская категория'
    )
    isactive = models.BooleanField('Активна', default=True)

    class Meta:
        verbosename = 'Категория'
        verbosenameplural = 'Категории'
        ordering = ['name']

    def str(self) -> str:
        return self.name


class Source(TimeStampedModel):
    """Источник данных (сайт, API, файл)"""

    class SourceType(models.TextChoices):
        HTML = 'html', 'HTML сайт'
        API = 'api', 'API'
        CSV = 'csv', 'CSV файл'
        XLSX = 'xlsx', 'Excel файл'
        JSON = 'json', 'JSON файл'

    name = models.CharField('Название', maxlength=255, unique=True)
    sourcetype = models.CharField('Тип источника', maxlength=10, choices=SourceType.choices)
    baseurl = models.URLField('Базовый URL', validators=[URLValidator()], blank=True)
    isactive = models.BooleanField('Активен', default=True)
    parseinterval = models.IntegerField('Интервал парсинга (минуты)', default=60)
    lastparseat = models.DateTimeField('Последний парсинг', null=True, blank=True)

    # Настройки парсинга
    config = models.JSONField('Конфигурация', default=dict, blank=True)
    headers = models.JSONField('HTTP заголовки', default=dict, blank=True)

    class Meta:
        verbosename = 'Источник'
        verbosenameplural = 'Источники'
        ordering = 'name'

    def str(self) -> str:
        return f"{self.name} ({self.getsourcetypedisplay()})"


class Product(TimeStampedModel):
    """Товар"""

    class AvailabilityStatus(models.TextChoices):
        INSTOCK = 'instock', 'В наличии'
        OUTOFSTOCK = 'outofstock', 'Нет в наличии'
        PREORDER = 'preorder', 'Предзаказ'
        DISCONTINUED = 'discontinued', 'Снято с производства'

    # Основные поля
    externalid = models.CharField('Внешний ID', maxlength=255, dbindex=True)
    source = models.ForeignKey(Source, ondelete=models.CASCADE, relatedname='products', verbosename='Источник')

    # Информация о товаре
    name = models.CharField('Название', maxlength=500)
    slug = models.SlugField('Slug', maxlength=550, blank=True)
    article = models.CharField('Артикул', maxlength=255, blank=True, dbindex=True)
    brand = models.CharField('Бренд', maxlength=255, blank=True, dbindex=True)
    category = models.ForeignKey(
        Category,
        ondelete=models.SETNULL,
        null=True,
        blank=True,
        relatedname='products',
        verbosename='Категория'
    )

    # Цена и наличие
    price = models.DecimalField('Цена', maxdigits=10, decimalplaces=2, validators=[MinValueValidator(0)])
    oldprice = models.DecimalField('Старая цена', maxdigits=10, decimalplaces=2, null=True, blank=True)
    currency = models.CharField('Валюта', maxlength=3, default='RUB')
    availability = models.CharField(
        'Наличие',
        maxlength=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.INSTOCK
    )
    stockquantity = models.IntegerField('Количество на складе', null=True, blank=True)


    # Описание
    description = models.TextField('Описание', blank=True)
    short_description = models.TextField('Краткое описание', blank=True)
    specifications = models.JSONField('Характеристики', default=dict, blank=True)

    # Медиа
    image_url = models.URLField('URL изображения', max_length=1000, blank=True)
    images = models.JSONField('Дополнительные изображения', default=list, blank=True)

    # Ссылки
    url = models.URLField('Ссылка на товар', max_length=1000)

    # Метаданные
    rating = models.DecimalField('Рейтинг', max_digits=3, decimal_places=2, null=True, blank=True)
    reviews_count = models.IntegerField('Количество отзывов', default=0)
    is_active = models.BooleanField('Активен', default=True)

    # Служебные поля
    parse_count = models.IntegerField('Количество парсингов', default=0)
    last_parsed_at = models.DateTimeField('Последний парсинг', auto_now=True)
    hash = models.CharField('Хеш данных', max_length=64, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['-created_at']
        unique_together = [['source', 'external_id']]
        indexes = [
            models.Index(fields=['source', 'external_id']),
            models.Index(fields=['article']),
            models.Index(fields=['brand']),
            models.Index(fields=['price']),
            models.Index(fields=['availability']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.article})"

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)[:550]
        super().save(*args, **kwargs)


class PriceHistory(models.Model):
    """История изменения цен"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_history', verbose_name='Товар')
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2)
    old_price = models.DecimalField('Старая цена', max_digits=10, decimal_places=2, null=True, blank=True)
    availability = models.CharField('Наличие', max_length=20)
    recorded_at = models.DateTimeField('Записано', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'История цен'
        verbose_name_plural = 'История цен'
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['product', '-recorded_at']),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.price} ({self.recorded_at})"


class ParseRun(TimeStampedModel):
    """Запуск парсинга"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        RUNNING = 'running', 'Выполняется'
        SUCCESS = 'success', 'Успешно'
        FAILED = 'failed', 'Ошибка'
        PARTIAL = 'partial', 'Частично'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='parse_runs', verbose_name='Источник')
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.PENDING)

    started_at = models.DateTimeField('Начало', null=True, blank=True)
    finished_at = models.DateTimeField('Окончание', null=True, blank=True)

    # Статистика
    total_items = models.IntegerField('Всего элементов', default=0)
    new_items = models.IntegerField('Новых', default=0)
    updated_items = models.IntegerField('Обновлено', default=0)
    failed_items = models.IntegerField('Ошибок', default=0)

    # Логи
    log = models.TextField('Лог', blank=True)
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    error_traceback = models.TextField('Traceback', blank=True)

    class Meta:
        verbose_name = 'Запуск парсинга'
        verbose_name_plural = 'Запуски парсинга'
        ordering = ['-created_at']


    def __str__(self)-> str:
        return f"{self.source.name} - {self.get_status_display()} ({self.created_at})"


    @property
    def duration(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class ParseError(TimeStampedModel):
    """Ошибки парсинга"""
    parse_run = models.ForeignKey(ParseRun, on_delete=models.CASCADE, related_name='errors', verbose_name='Запуск')
    url = models.URLField('URL', max_length=1000, blank=True)
    error_type = models.CharField('Тип ошибки', max_length=255)
    error_message = models.TextField('Сообщение')
    traceback = models.TextField('Traceback', blank=True)
    data = models.JSONField('Данные', default=dict, blank=True)

    class Meta:
        verbose_name = 'Ошибка парсинга'
        verbose_name_plural = 'Ошибки парсинга'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.error_type} - {self.created_at}"
