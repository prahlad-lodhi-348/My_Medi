# api/tasks.py
# Celery tasks — missed dose detect, push notification, 7-day email report

import logging
from datetime import date, timedelta, datetime

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone


from .models import (
    IntakeLog, Caregiver, NotificationLog, DoseTime, Regimen, User
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPER: Expo Push Notification bhejna
# ─────────────────────────────────────────────
def send_expo_push(token: str, title: str, body: str, data: dict | None = None) -> bool:

    """
    Expo Push API se notification bhejo.
    Returns True if sent successfully.
    """
    if not token or not token.startswith("ExponentPushToken["):
        logger.warning(f"Invalid Expo token: {token}")
        return False

    payload = {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": data or {},
    }

    try:
        resp = requests.post(
            "https://exp.host/--/api/v2/push/send",
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        # Expo returns JSON on both success/failure.
        try:
            result = resp.json()
        except Exception:
            result = {"raw": resp.text}

        # Expo returns {"data": {"status": "ok"}} on success.
        if result.get("data", {}).get("status") == "ok":
            return True

        logger.error(
            "Expo push failed (HTTP %s): %s",
            resp.status_code,
            result,
        )
        return False
    except Exception:
        logger.exception("Expo push exception")
        return False



# ─────────────────────────────────────────────
# TASK 1: Missed dose detect karo + caregiver ko push bhejo
# Yeh task har 30 min mein chalega (Celery Beat se)
# ─────────────────────────────────────────────
@shared_task(bind=True, max_retries=3)
def check_missed_doses(self):
    """
    PENDING IntakeLogs dhundo jinka time 30+ min pehle tha.
    Unhe MISSED mark karo.
    Caregiver ko push notification bhejo (agar notify_on_missed=True).
    """
    now = timezone.localtime(timezone.now())
    today = now.date()
    cutoff_time = (now - timedelta(minutes=30)).time()

    # PENDING logs jo aaj ke hain aur time nikal gaya
    missed_logs = IntakeLog.objects.filter(
        date=today,
        status='PENDING',
        dose_time__time__lte=cutoff_time,
    ).select_related(
        'user', 'regimen', 'regimen__medicine', 'dose_time'
    )

    for log in missed_logs:
        # Status update karo
        log.status = 'MISSED'
        log.save(update_fields=['status'])

        # Patient ke active caregivers dhundo
        caregivers = Caregiver.objects.filter(
            patient=log.user,
            is_active=True,
            notify_on_missed=True,
        )

        medicine_name = log.regimen.medicine.name
        dose_time_str = log.dose_time.time.strftime("%I:%M %p")

        title = "Dose Missed!"
        body = (
            f"{log.user.get_full_name() or log.user.username} ne "
            f"{medicine_name} ({dose_time_str}) nahi li."
        )

        for caregiver in caregivers:
            status = 'FAILED'
            error = None

            # Push notification (agar token hai)
            if caregiver.expo_push_token:
                success = send_expo_push(
                    token=caregiver.expo_push_token,
                    title=title,
                    body=body,
                    data={
                        "type": "MISSED_DOSE",
                        "intake_log_id": log.id,
                        "patient_id": log.user.id,
                    }
                )
                status = 'SENT' if success else 'FAILED'
                if not success:
                    error = "Expo push delivery failed"
            else:
                error = "No expo token registered"

            # Log karo
            NotificationLog.objects.create(
                patient=log.user,
                caregiver=caregiver,
                notification_type='MISSED_DOSE',
                channel='PUSH',
                status=status,
                title=title,
                body=body,
                intake_log=log,
                error_message=error,
            )

    logger.info(f"check_missed_doses: {missed_logs.count()} logs processed")
    return f"Processed {missed_logs.count()} missed doses"


# ─────────────────────────────────────────────
# TASK 2: 7-Din ka Weekly Report Email
# Har Sunday raat 8 baje chalega
# ─────────────────────────────────────────────
@shared_task(bind=True, max_retries=3)
def send_weekly_caregiver_report(self):
    """
    Har active caregiver ko unke patient ki
    7-din ki adherence report email karo.
    """
    today = date.today()
    week_start = today - timedelta(days=6)  # last 7 days

    # Sabhi active caregivers jo email rakhte hain
    caregivers = Caregiver.objects.filter(
        is_active=True,
        email__isnull=False,
    ).exclude(email='').select_related('patient')

    sent_count = 0

    for caregiver in caregivers:
        try:
            report_data = _build_weekly_report(
                patient=caregiver.patient,
                week_start=week_start,
                week_end=today,
            )

            # HTML email render karo
            html_content = render_to_string(
                'emails/weekly_caregiver_report.html',
                {
                    'caregiver': caregiver,
                    'patient': caregiver.patient,
                    'report': report_data,
                    'week_start': week_start,
                    'week_end': today,
                }
            )
            plain_content = _build_plain_report(caregiver, report_data, week_start, today)

            subject = (
                f"Weekly Report: {caregiver.patient.get_full_name() or caregiver.patient.username} "
                f"({week_start.strftime('%d %b')} - {today.strftime('%d %b')})"
            )

            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[caregiver.email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()

            # Log karo
            NotificationLog.objects.create(
                patient=caregiver.patient,
                caregiver=caregiver,
                notification_type='WEEKLY_REPORT',
                channel='EMAIL',
                status='SENT',
                title=subject,
                body=plain_content[:500],
            )
            sent_count += 1

        except Exception as e:
            logger.error(f"Weekly report failed for caregiver {caregiver.id}: {e}")
            NotificationLog.objects.create(
                patient=caregiver.patient,
                caregiver=caregiver,
                notification_type='WEEKLY_REPORT',
                channel='EMAIL',
                status='FAILED',
                title="Weekly Report",
                body="",
                error_message=str(e),
            )

    logger.info(f"send_weekly_caregiver_report: {sent_count} emails sent")
    return f"Sent {sent_count} weekly reports"


def _build_weekly_report(patient, week_start, week_end):
    """
    Patient ke 7-din ke IntakeLogs se stats banao.
    """
    logs = IntakeLog.objects.filter(
        user=patient,
        date__range=[week_start, week_end],
    ).select_related('regimen__medicine', 'dose_time')

    total = logs.count()
    taken = logs.filter(status='TAKEN').count()
    missed = logs.filter(status='MISSED').count()
    skipped = logs.filter(status='SKIPPED').count()
    adherence_pct = round((taken / total * 100) if total > 0 else 0)

    # Per-medicine breakdown
    medicine_stats = {}
    for log in logs:
        med_name = log.regimen.medicine.name
        if med_name not in medicine_stats:
            medicine_stats[med_name] = {'taken': 0, 'missed': 0, 'skipped': 0, 'total': 0}
        medicine_stats[med_name]['total'] += 1
        if log.status in ('TAKEN', 'MISSED', 'SKIPPED'):
            medicine_stats[med_name][log.status.lower()] += 1

    # Per-day breakdown
    day_stats = {}
    current = week_start
    while current <= week_end:
        day_logs = logs.filter(date=current)
        day_taken = day_logs.filter(status='TAKEN').count()
        day_total = day_logs.count()
        day_stats[current.strftime('%a, %d %b')] = {
            'taken': day_taken,
            'total': day_total,
            'pct': round((day_taken / day_total * 100) if day_total > 0 else 0),
        }
        current += timedelta(days=1)

    return {
        'total': total,
        'taken': taken,
        'missed': missed,
        'skipped': skipped,
        'adherence_pct': adherence_pct,
        'medicine_stats': medicine_stats,
        'day_stats': day_stats,
    }


def _build_plain_report(caregiver, report, week_start, week_end):
    """Plain text fallback for email clients that block HTML."""
    patient_name = caregiver.patient.get_full_name() or caregiver.patient.username
    lines = [
        f"MyMedi — Weekly Report",
        f"Patient: {patient_name}",
        f"Period: {week_start.strftime('%d %b')} to {week_end.strftime('%d %b')}",
        f"",
        f"Overall Adherence: {report['adherence_pct']}%",
        f"Doses Taken:   {report['taken']}",
        f"Doses Missed:  {report['missed']}",
        f"Doses Skipped: {report['skipped']}",
        f"",
        f"Per Medicine:",
    ]
    for med, stats in report['medicine_stats'].items():
        pct = round((stats['taken'] / stats['total'] * 100) if stats['total'] > 0 else 0)
        lines.append(f"  {med}: {pct}% ({stats['taken']}/{stats['total']} taken)")
    lines += ["", "Daily Breakdown:"]
    for day, stats in report['day_stats'].items():
        lines.append(f"  {day}: {stats['taken']}/{stats['total']} doses ({stats['pct']}%)")
    return "\n".join(lines)