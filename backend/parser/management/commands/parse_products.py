from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet

from core.models import Source
from parser.tasks import parse_source_task


class Command(BaseCommand):
    """Django management command: запускает парсинг товаров из источников."""
    help = 'Запустить парсинг товаров'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            '--source',
            type=int,
            help='ID источника для парсинга'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Парсить все активные источники'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            dest='async_mode',
            help='Запустить парсинг асинхронно через Celery'
        )
        parser.add_argument(
            '--details',
            action='store_true',
            help='Загружать детальную информацию о товарах'
        )
        parser.add_argument(
            '--no-deactivate',
            action='store_true',
            help='Не деактивировать отсутствующие товары'
        )

    def handle(self, *args, **options: Any) -> None:
        """Валидирует опции, выбирает источники и запускает парсинг (sync/async)."""
        source_id = options.get('source')
        parse_all = options.get('all')
        async_mode = options.get('async_mode')
        fetch_details = options.get('details')
        deactivate_missing = not options.get('no_deactivate')

        if not source_id and not parse_all:
            self.stdout.write(self.style.ERROR(
                'Укажите --source <ID> или --all'
            ))
            return

        # Получаем источники для парсинга
        if parse_all:
            sources = Source.objects.filter(is_active=True)
        else:
            sources = Source.objects.filter(id=source_id, is_active=True)

        if not sources.exists():
            self.stdout.write(self.style.ERROR('Источники не найдены'))
            return

        kwargs = {
            'fetch_details': fetch_details,
            'deactivate_missing': deactivate_missing
        }

        for source in sources:
            self.stdout.write(f'Парсинг источника: {source.name}')

            if async_mode:
                # Асинхронный запуск через Celery
                task = parse_source_task.delay(source.id, **kwargs)
                self.stdout.write(self.style.SUCCESS(
                    f'Задача запущена: {task.id}'
                ))
            else:
                # Синхронный запуск
                result = parse_source_task(source.id, **kwargs)

                if result.get("status") == 'success':
                    self.stdout.write(self.style.SUCCESS(
                        f"Успешно: новых={result['new']}, "
                        f"обновлено={result['updated']}, "
                        f"ошибок={result['failed']}"
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"Ошибка: {result.get('error')}"
                    ))
