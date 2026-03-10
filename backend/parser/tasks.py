from celery import shared_task
from django.utils import timezone
from typing import Any, Sequence
import traceback
import logging

from core.models import Source, ParseRun, ParseError
from .extractors import get_extractor
from .utils import save_or_update_product, deactivate_missing_products

logger: logging.Logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def parse_source_task(self, source_id: int, **kwargs: Any) -> dict[str, Any]:
    """Celery задача для парсинга источника товаров."""

    try:
        source: Source = Source.objects.get(id=source_id, is_active=True)
    except Source.DoesNotExist:
        logger.error(f"Источник {source_id} не найден или неактивен")
        return {'error': 'Source not found'}

    # Создаем запуск парсинга
    parse_run: ParseRun = ParseRun.objects.create(
        source=source,
        status='running',
        started_at=timezone.now()
    )

    log_messages: list[str] = []

    try:
        log_messages.append(f"Начало парсинга источника: {source.name}")

        # Получаем экстрактор
        extractor = get_extractor(source)

        # Извлекаем список товаров
        log_messages.append("Извлечение списка товаров...")
        items: list[dict[str, Any]] = extractor.extract_list(**kwargs)

        parse_run.total_items = len(items)
        parse_run.save()

        log_messages.append(f"Найдено товаров: {len(items)}")

        # Обрабатываем товары
        new_count: int = 0
        updated_count: int = 0
        failed_count: int = 0
        active_external_ids: list[str] = []

        for i: int, item_data: dict[str, Any] in enumerate(items, 1):
        try:
            # Опционально: извлечь детальную информацию
            if kwargs.get('fetch_details', False):
                item_data = extractor.extract_detail(item_data)

            # Сохраняем товар
            product, created, updated = save_or_update_product(
                source, item_data, parse_run
            )

            if product:
                active_external_ids.append(product.external_id)

                if created:
                    new_count += 1
                elif updated:
                    updated_count += 1
            else:
                failed_count += 1

            # Логируем прогресс каждые 100 товаров
            if i % 100 == 0:
                log_messages.append(f"Обработано {i}/{len(items)} товаров")
                parse_run.log = '\n'.join(log_messages)
                parse_run.save()

        except Exception as e:
            failed_count += 1
            logger.error(f"Ошибка обработки товара: {e}")

            ParseError.objects.create(
                parse_run=parse_run,
                error_type='item_processing_error',
                error_message=str(e),
                traceback=traceback.format_exc(),
                data=item_data
            )

    # Деактивируем отсутствующие товары
    if kwargs.get('deactivate_missing', True):
        deactivated: int = deactivate_missing_products(source, active_external_ids)
        log_messages.append(f"Деактивировано товаров: {deactivated}")

    # Обновляем статистику
    parse_run.new_items = new_count
    parse_run.updated_items = updated_count
    parse_run.failed_items = failed_count
    parse_run.status = 'success' if failed_count == 0 else 'partial'
    parse_run.finished_at = timezone.now()
    parse_run.log = '\n'.join(log_messages)
    parse_run.save()

    # Обновляем источник
    source.last_parse_at = timezone.now()
    source.save()

    log_messages.append("Парсинг завершен успешно")
    logger.info(f"Парсинг {source.name} завершен: новых={new_count}, обновлено={updated_count}, ошибок={failed_count}")

    return {
        'source': source.name,
        'status': 'success',
        'total': len(items),
        'new': new_count,
        'updated': updated_count,
        'failed': failed_count
    }

except Exception as e:
error_msg: str = str(e)
error_trace: str = traceback.format_exc()

logger.error(f"Критическая ошибка парсинга {source.name}: {error_msg}")

parse_run.status = 'failed'
parse_run.finished_at = timezone.now()
parse_run.error_message = error_msg
parse_run.error_traceback = error_trace
parse_run.log = '\n'.join(log_messages)
parse_run.save()

# Повторяем задачу при ошибке
if self.request.retries < self.max_retries:
    raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

return {
    'source': source.name,
    'status': 'failed',
    'error': error_msg
}
