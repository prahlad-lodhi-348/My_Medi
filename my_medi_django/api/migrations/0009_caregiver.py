# Generated manually for Caregiver model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_regimenmedicine_brand_regimenmedicine_description_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Caregiver',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=15)),
                ('relationship', models.CharField(max_length=50)),
                ('notify_on_missed', models.BooleanField(default=True)),
                ('notify_on_low_stock', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='caregivers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('patient', 'phone')},
            },
        ),
    ]

