"""
Management command: check_missed_doses

Usage:
    python manage.py check_missed_doses

Runs the missed dose detection engine. Suitable for cron jobs,
Windows Task Scheduler, or any external periodic runner.
"""

from django.core.management.base import BaseCommand
from api.dose_detection import check_missed_doses


class Command(BaseCommand):
    help = "Run missed dose detection engine and create SKIPPED logs for missed doses"

    def handle(self, *args, **options):
        count = check_missed_doses()
        self.stdout.write(
            self.style.SUCCESS(
                f"Missed dose check complete. Created {count} SKIPPED intake log(s)."
            )
        )

