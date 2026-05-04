from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid
import json


def default_days_of_week():
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class User(AbstractUser):
    email = models.EmailField(unique = True ) 
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(null=True, blank=True, default=uuid.uuid4)

    def generate_verification_token(self):
        self.email_verification_token = uuid.uuid4()
        self.save()
        return self.email_verification_token

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    caregiver = models.CharField(max_length=100, blank=True, null=True)
    step_count = models.IntegerField(default=0)
    water_intake = models.IntegerField(default=0)
    

    def __str__(self):
        return f"{self.user.username}'s Profile"
    

class Caregiver(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="caregivers")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    relationship = models.CharField(max_length=50)
    notify_on_missed = models.BooleanField(default=True)
    notify_on_low_stock = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(blank=True, null=True)
    expo_push_token = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        unique_together = ("patient", "phone")

    def __str__(self):
        return f"{self.name} ({self.relationship}) - {self.patient.username}"


class Medicine(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    dosage = models.CharField(max_length=50, null=True, blank=True, default=None)
    frequency = models.CharField(max_length=50, null=True, blank=True, default=None)
    notes = models.TextField(blank=True, default='', null=True)
    image = models.ImageField(upload_to='medicines/', blank=True, null=True)
    working_mechanism = models.TextField(blank=True, default='Information not available')
    side_effects = models.TextField(blank=True, default='Information not available')
    is_taken = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"


# ============ PHASE 2 MODELS ============

class RegimenMedicine(models.Model):
    FORM_CHOICES = [
        ('TABLET', 'Tablet'),
        ('CAPSULE', 'Capsule'),
        ('SYRUP', 'Syrup'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    form = models.CharField(max_length=10, choices=FORM_CHOICES)
    strength = models.CharField(max_length=100)
    brand = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to='medicines/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.form}) - {self.user.username}"


class Regimen(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    medicine = models.ForeignKey(RegimenMedicine, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    instructions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.medicine.name} - {self.user.username}"


class DoseTime(models.Model):
    UNIT_CHOICES = [
        ('TABLET', 'Tablet'),
        ('CAPSULE', 'Capsule'),
        ('ML', 'Milliliter'),
    ]
    
    regimen = models.ForeignKey(Regimen, on_delete=models.CASCADE, related_name='dose_times')
    time = models.TimeField()
    label = models.CharField(max_length=100, blank=True, default='')
    quantity = models.DecimalField(max_digits=5, decimal_places=1)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    days_of_week = models.JSONField(default=default_days_of_week)

    class Meta:
        ordering = ['time']

    def __str__(self):
        return f"{self.regimen.medicine.name} @ {self.time} ({self.quantity}{self.unit})"

    def clean(self):
        medicine_form = self.regimen.medicine.form
        
        # SYRUP must use ML
        if medicine_form == 'SYRUP':
            if self.unit != 'ML':
                raise ValidationError(f"SYRUP medicine must use ML, got {self.unit}")
        
        # TABLET must use TABLET
        elif medicine_form == 'TABLET':
            if self.unit != 'TABLET':
                raise ValidationError(f"TABLET medicine must use TABLET, got {self.unit}")
            # Quantity must be in 0.5 steps (0.5, 1, 1.5, 2, etc.)
            if self.quantity % Decimal('0.5') != 0:
                raise ValidationError("TABLET quantity must be in 0.5 steps (0.5, 1, 1.5, ...)")
        
        # CAPSULE must use CAPSULE
        elif medicine_form == 'CAPSULE':
            if self.unit != 'CAPSULE':
                raise ValidationError(f"CAPSULE medicine must use CAPSULE, got {self.unit}")
            # Quantity must be integer
            if self.quantity != self.quantity.to_integral_value():
                raise ValidationError("CAPSULE quantity must be an integer")


class Stock(models.Model):
    regimen = models.OneToOneField(Regimen, on_delete=models.CASCADE, related_name='stock')
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=10, choices=DoseTime.UNIT_CHOICES)
    low_stock_threshold_days = models.IntegerField(default=3)
    reorder_url = models.URLField(blank=True, default='')
    last_low_stock_seen_at = models.DateTimeField(null=True, blank=True)
    last_reorder_response = models.CharField(max_length=10, null=True, blank=True)
    last_reorder_response_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Stock for {self.regimen.medicine.name} ({self.current_quantity}{self.unit})"

    def clean(self):
        medicine_form = self.regimen.medicine.form
        
        # Validate unit matches medicine form
        if medicine_form == 'SYRUP' and self.unit != 'ML':
            raise ValidationError(f"SYRUP medicine must use ML, got {self.unit}")
        elif medicine_form == 'TABLET' and self.unit != 'TABLET':
            raise ValidationError(f"TABLET medicine must use TABLET, got {self.unit}")
        elif medicine_form == 'CAPSULE' and self.unit != 'CAPSULE':
            raise ValidationError(f"CAPSULE medicine must use CAPSULE, got {self.unit}")


class IntakeLog(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('TAKEN', 'Taken'),
        ('SKIPPED', 'Skipped'),
        ('MISSED', 'Missed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    regimen = models.ForeignKey(Regimen, on_delete=models.CASCADE, related_name='intake_logs')
    dose_time = models.ForeignKey(DoseTime, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    taken_at = models.DateTimeField(null=True, blank=True)
    quantity = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    unit = models.CharField(max_length=10, choices=DoseTime.UNIT_CHOICES, null=True, blank=True)

    class Meta:
        unique_together = ('regimen', 'dose_time', 'date')
        ordering = ['-date', 'dose_time__time']

    def __str__(self):
        return f"{self.regimen.medicine.name} - {self.date} ({self.status})"




#  this is phase 3 related code notification  


class NotificationLog(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('MISSED_DOSE', 'Missed Dose'),
        ('LOW_STOCK', 'Low Stock'),
        ('WEEKLY_REPORT', 'Weekly Report'),
        ('DOSE_REMINDER', 'Dose Reminder'),
    ]
    CHANNEL_CHOICES = [
        ('PUSH', 'Push Notification'),
        ('EMAIL', 'Email'),
    ]
    STATUS_CHOICES = [
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('PENDING', 'Pending'),
    ]
 
    # Kis patient ke liye (regarding )
    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notification_logs'
    )
    # Kaun receive karega (caregiver ya patient khud)
    caregiver = models.ForeignKey(
        'Caregiver',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notification_logs'
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
 
    # Kya message gaya
    title = models.CharField(max_length=200)
    body = models.TextField()
 
    # Related dose (optional — missed dose ke liye)
    intake_log = models.ForeignKey(
        'IntakeLog',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications'
    )
 
    sent_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True, null=True)
 
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['patient', 'notification_type']),
            models.Index(fields=['caregiver', 'sent_at']),
        ]
 
    def __str__(self):
        return f"{self.notification_type} → {self.caregiver or self.patient} [{self.status}]"

