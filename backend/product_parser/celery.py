import os
from typing import Any, Dict

from celery import Celery
from celery.schedules import crontab
from celery.app.task import Task

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product_parser.settings')

app = Celery('product_parser')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Периодические задачи
app.conf.beat_schedule: Dict[str, Dict[str, Any]] = {
    'parse-all-sources-every-hour': {
        'task': 'tasks.tasks.parse_all_active_sources',
        'schedule': crontab(minute=0),  # Каждый час
    },
    'cleanup-old-parse-runs': {
        'task': 'tasks.tasks.cleanup_old_parse_runs',
        'schedule': crontab(hour=3, minute=0),  # Каждый день в 3:00
    },
}


@app.task(bind=True)
def debug_task(self: Task) -> None:
    print(f'Request: {self.request!r}')
