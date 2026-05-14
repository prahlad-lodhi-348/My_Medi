from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile, Medicine

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm')

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    is_email_verified = serializers.BooleanField(source='user.is_email_verified', read_only=True)
    age = serializers.SerializerMethodField(read_only=True)
    caregiver = serializers.CharField(max_length=100, allow_blank=True, required=False)

    def get_age(self, obj):
        if not obj.date_of_birth:
            return None
        from datetime import date
        today = date.today()
        dob = obj.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    class Meta:
        model = Profile
        fields = [
            'id', 'user',
            'username', 'email', 'is_email_verified',
            'phone', 'date_of_birth', 'age', 'gender', 'caregiver',
            'step_count', 'water_intake',
        ]
        read_only_fields = ['id', 'user', 'username', 'email', 'is_email_verified', 'age']


class MedicineSerializer(serializers.ModelSerializer):
    # Make fields optional with allow_blank=True for serializer validation
    dosage = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    frequency = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    working_mechanism = serializers.CharField(required=False, allow_blank=True, default='Information not available')
    side_effects = serializers.CharField(required=False, allow_blank=True, default='Information not available')

    class Meta:
        model = Medicine
        fields = '__all__'


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()