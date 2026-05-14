"""
Django signals for caregiver escalation.

Triggered when an IntakeLog is created with status='SKIPPED'.
Covers both:
  - Automatic missed-dose detection (dose_detection.check_missed_doses)
  - Manual SKIP action by the patient (IntakeUpsertView)
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import IntakeLog, Caregiver


@receiver(post_save, sender=IntakeLog)
def notify_caregivers_on_skipped(sender, instance, created, **kwargs):
    """
    Signal handler: when an IntakeLog is created with status='SKIPPED',
    notify all active caregivers configured for missed-dose alerts.

    This is a placeholder hook. Replace the pass statements with actual
    SMS/email/push integration.
    """
    if not created:
        return

    if instance.status != "SKIPPED":
        return

    user = instance.user
    caregivers = Caregiver.objects.filter(
        patient=user,
        notify_on_missed=True,
        is_active=True,
    )

    for caregiver in caregivers:
        # Placeholder: trigger escalation notification event
        # TODO: integrate SMS/email/push notification later
        # Example:
        # send_sms(caregiver.phone, f"{user.username} missed a dose of {instance.regimen.medicine.name}.")
        pass

