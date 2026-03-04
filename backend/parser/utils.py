import logging
from typing import Any, Dict, Optional, Sequence, Tuple

from django.db.models import QuerySet
from django.utils import timezone

from core.models import PriceHistory, Product, Source  # Source укажите/исправьте импорт под ваш проект

logger = logging.getLogger(__name__)


def save_or_update_product(
    source: Source,
    item_data: Dict[str, Any],
    parse_run: Optional["ParseRun"] = None,  # если есть модель ParseRun, лучше импортировать напрямую
) -> Tuple[Optional[Product], bool, bool]:
    """
    Сохранить или обновить товар
    Возвращает (product, created, updated)
    """
    external_id: Optional[str] = item_data.get("external_id")

    if not external_id:
        logger.warning(f"Товар без external_id: {item_data.get('name')}")
        return None, False, False

    try:
        product: Optional[Product] = (
            Product.objects.filter(source=source, external_id=external_id).first()
        )

        created: bool = False
        updated: bool = False

        if product:
            old_price: Any = product.price
            old_availability: Any = product.availability

            for field, value in item_data.items():
                if hasattr(product, field) and value is not None:
                    setattr(product, field, value)

            product.parse_count = int(product.parse_count) + 1
            product.last_parsed_at = timezone.now()
            product.save()

            if old_price != product.price or old_availability != product.availability:
                PriceHistory.objects.create(
                    product=product,
                    price=product.price,
                    old_price=product.old_price,
                    availability=product.availability,
                )
                updated = True
        else:
            product = Product.objects.create(
                source=source,
                external_id=external_id,
                **{k: v for k, v in item_data.items() if k != "external_id"},
            )

            PriceHistory.objects.create(
                product=product,
                price=product.price,
                old_price=product.old_price,
                availability=product.availability,
            )
            created = True

        return product, created, updated

    except Exception as e:
        logger.error(f"Ошибка сохранения товара {external_id}: {e}")

        if parse_run:
            from core.models import ParseError  # чтобы не делать импорт на модульном уровне

            ParseError.objects.create(
                parse_run=parse_run,
                error_type="save_error",
                error_message=str(e),
                data=item_data,
            )

        return None, False, False


def deactivate_missing_products(
    source: Source,
    active_external_ids: Sequence[str],
) -> int:
    """Деактивировать товары, которых нет в новом парсинге"""
    missing_products: QuerySet[Product] = (
        Product.objects.filter(source=source, is_active=True).exclude(
            external_id__in=active_external_ids
        )
    )

    count: int = missing_products.count()

    if count > 0:
        missing_products.update(is_active=False, availability="out_of_stock")
        logger.info(f"Деактивировано {count} товаров")

    return count
