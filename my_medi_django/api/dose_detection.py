"""
Missed Dose Detection Engine

Callable function to scan all active regimens and mark doses as SKIPPED
if the current time has passed the scheduled dose time + 30 minutes
and no IntakeLog exists yet.
"""

from datetime import datetime, date, timedelta
from django.utils import timezone

from .models import Regimen, DoseTime, IntakeLog


GRACE_PERIOD_MINUTES = 30


def check_missed_doses():
    """
    Scan all active regimens for doses that have passed their scheduled time
    by more than GRACE_PERIOD_MINUTES (30 minutes).

    For each missed dose without an existing IntakeLog, creates an IntakeLog
    with status='SKIPPED'. This triggers the caregiver escalation signal.

    Returns:
        int: Number of newly created SKIPPED IntakeLog entries.
    """
    now = timezone.now()
    today = now.date()
    day_name = today.strftime("%a")

    missed_count = 0

    active_regimens = Regimen.objects.filter(is_active=True).select_related(
        "user", "medicine"
    ).prefetch_related("dose_times")

    for regimen in active_regimens:
        # Only process regimens whose start_date <= today <= end_date (if end_date set)
        if regimen.start_date > today:
            continue
        if regimen.end_date and regimen.end_date < today:
            continue

        dose_times = regimen.dose_times.all()

        for dt in dose_times:
            days_of_week = (
                dt.days_of_week
                if dt.days_of_week
                else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            )

            # Short and full names are both acceptable in days_of_week
            if day_name not in days_of_week and day_name[:3] not in days_of_week:
                continue

            scheduled_naive = datetime.combine(today, dt.time)
            # Make it timezone-aware using the system's timezone
            scheduled = timezone.make_aware(scheduled_naive)
            grace_deadline = scheduled + timedelta(minutes=GRACE_PERIOD_MINUTES)

            if now <= grace_deadline:
                # Dose is still within the grace period
                continue

            # Check if IntakeLog already exists for this regimen, dose_time, date
            exists = IntakeLog.objects.filter(
                regimen=regimen,
                dose_time=dt,
                date=today,
            ).exists()

            if exists:
                continue

            # Create SKIPPED log — signal will trigger caregiver escalation
            IntakeLog.objects.create(
                user=regimen.user,
                regimen=regimen,
                dose_time=dt,
                date=today,
                status="SKIPPED",
                quantity=dt.quantity,
                unit=dt.unit,
            )
            missed_count += 1

    return missed_count

