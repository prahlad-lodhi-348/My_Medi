"""Celery configuration for my_medi_backend.

Celery uses this module when you run:
  celery -A my_medi_backend worker -l info
  celery -A my_medi_backend beat -l info

Do not create a root-level celery.py file, because it shadows the celery package.
"""


from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_medi_backend.settings")

app = Celery("my_medi_backend")

# Load all CELERY_* settings from Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in installed apps.
app.autodiscover_tasks()


