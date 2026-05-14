from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

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
    step_count = models.IntegerField(default=0)
    water_intake = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Medicine(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    dosage = models.CharField(max_length=50)
    frequency = models.CharField(max_length=50)
    notes = models.TextField(blank=True)
    image = models.ImageField(upload_to='medicines/', blank=True, null=True)
    working_mechanism = models.TextField(blank=True, default='Information not available')
    side_effects = models.TextField(blank=True, default='Information not available')
    is_taken = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"



