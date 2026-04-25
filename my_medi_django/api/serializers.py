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
    class Meta:
        model = Profile
        fields = '__all__'

class MedicineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medicine
        fields = '__all__'

class LoginSerializer(serializers.Serializer):
    # username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField()

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


    from rest_framework import serializers
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import (
    RegimenMedicine, Regimen, DoseTime, Stock, IntakeLog, User
)


class RegimenMedicineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimenMedicine
        fields = ['id', 'name', 'form', 'strength', 'notes']

    def validate_form(self, value):
        if value not in ['TABLET', 'CAPSULE', 'SYRUP']:
            raise serializers.ValidationError("form must be TABLET, CAPSULE, or SYRUP")
        return value


class DoseTimeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoseTime
        fields = ['id', 'time', 'label', 'quantity', 'unit', 'days_of_week']

    def validate(self, data):
        regimen = self.context.get('regimen')
        if not regimen:
            return data
        
        medicine_form = regimen.medicine.form
        unit = data.get('unit')
        quantity = data.get('quantity')
        
        # SYRUP => ML only
        if medicine_form == 'SYRUP':
            if unit != 'ML':
                raise serializers.ValidationError(
                    f"SYRUP medicine must use ML, got {unit}"
                )
        
        # TABLET => TABLET only, quantity in 0.5 steps
        elif medicine_form == 'TABLET':
            if unit != 'TABLET':
                raise serializers.ValidationError(
                    f"TABLET medicine must use TABLET, got {unit}"
                )
            if quantity % Decimal('0.5') != 0:
                raise serializers.ValidationError(
                    "TABLET quantity must be in 0.5 steps (0.5, 1, 1.5, ...)"
                )
        
        # CAPSULE => CAPSULE only, integer quantity
        elif medicine_form == 'CAPSULE':
            if unit != 'CAPSULE':
                raise serializers.ValidationError(
                    f"CAPSULE medicine must use CAPSULE, got {unit}"
                )
            if quantity != quantity.to_integral_value():
                raise serializers.ValidationError(
                    "CAPSULE quantity must be an integer"
                )
        
        return data


class StockCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ['id', 'current_quantity', 'unit', 'low_stock_threshold_days', 'reorder_url']

    def validate(self, data):
        regimen = self.context.get('regimen')
        if not regimen:
            return data
        
        medicine_form = regimen.medicine.form
        unit = data.get('unit')
        
        # Validate unit matches medicine form
        if medicine_form == 'SYRUP' and unit != 'ML':
            raise serializers.ValidationError(
                f"SYRUP medicine must use ML, got {unit}"
            )
        elif medicine_form == 'TABLET' and unit != 'TABLET':
            raise serializers.ValidationError(
                f"TABLET medicine must use TABLET, got {unit}"
            )
        elif medicine_form == 'CAPSULE' and unit != 'CAPSULE':
            raise serializers.ValidationError(
                f"CAPSULE medicine must use CAPSULE, got {unit}"
            )
        
        return data


class RegimenCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regimen
        fields = ['id', 'medicine', 'start_date', 'end_date', 'instructions', 'is_active']


class RegimenReadSerializer(serializers.ModelSerializer):
    medicine = RegimenMedicineCreateSerializer(read_only=True)
    dose_times = DoseTimeCreateSerializer(many=True, read_only=True)
    stock = StockCreateSerializer(read_only=True)

    class Meta:
        model = Regimen
        fields = ['id', 'medicine', 'start_date', 'end_date', 'instructions', 'is_active', 'created_at', 'dose_times', 'stock']


class IntakeUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntakeLog
        fields = ['id', 'regimen', 'dose_time', 'date', 'status', 'taken_at', 'quantity', 'unit']

    def validate(self, data):
        regimen = data.get('regimen')
        dose_time = data.get('dose_time')
        date = data.get('date')
        
        # Ensure dose_time belongs to regimen
        if dose_time and dose_time.regimen != regimen:
            raise serializers.ValidationError(
                "dose_time does not belong to the specified regimen"
            )
        
        return data


class StockPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ['current_quantity', 'low_stock_threshold_days', 'reorder_url']


class StockRestockSerializer(serializers.Serializer):
    add_quantity = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_add_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("add_quantity must be positive")
        return value


class StockReorderResponseSerializer(serializers.Serializer):
    ordered = serializers.BooleanField()


class RegimenWizardSerializer(serializers.Serializer):
    medicine = RegimenMedicineCreateSerializer()
    regimen = RegimenCreateSerializer()
    dose_times = serializers.ListField(child=serializers.DictField())
    stock = StockCreateSerializer()

    def validate(self, data):
        medicine_data = data.get('medicine')
        dose_times_data = data.get('dose_times', [])
        stock_data = data.get('stock')
        
        medicine_form = medicine_data.get('form')
        
        # Validate each dose_time against medicine form
        for dt in dose_times_data:
            unit = dt.get('unit')
            quantity = dt.get('quantity', Decimal('1'))
            
            if medicine_form == 'SYRUP':
                if unit != 'ML':
                    raise serializers.ValidationError(
                        f"SYRUP medicine must use ML, got {unit}"
                    )
            elif medicine_form == 'TABLET':
                if unit != 'TABLET':
                    raise serializers.ValidationError(
                        f"TABLET medicine must use TABLET, got {unit}"
                    )
                quantity = Decimal(str(quantity))
                if quantity % Decimal('0.5') != 0:
                    raise serializers.ValidationError(
                        "TABLET quantity must be in 0.5 steps"
                    )
            elif medicine_form == 'CAPSULE':
                if unit != 'CAPSULE':
                    raise serializers.ValidationError(
                        f"CAPSULE medicine must use CAPSULE, got {unit}"
                    )
                quantity = Decimal(str(quantity))
                if quantity != quantity.to_integral_value():
                    raise serializers.ValidationError(
                        "CAPSULE quantity must be an integer"
                    )
        
        # Validate stock unit matches medicine form
        stock_unit = stock_data.get('unit')
        if medicine_form == 'SYRUP' and stock_unit != 'ML':
            raise serializers.ValidationError(
                f"SYRUP medicine must use ML in stock, got {stock_unit}"
            )
        elif medicine_form == 'TABLET' and stock_unit != 'TABLET':
            raise serializers.ValidationError(
                f"TABLET medicine must use TABLET in stock, got {stock_unit}"
            )
        elif medicine_form == 'CAPSULE' and stock_unit != 'CAPSULE':
            raise serializers.ValidationError(
                f"CAPSULE medicine must use CAPSULE in stock, got {stock_unit}"
            )
        
        return data

    @transaction.atomic
    def create(self, validated_data):
        user = self.context.get('user')
        medicine_data = validated_data.pop('medicine')
        regimen_data = validated_data.pop('regimen')
        dose_times_data = validated_data.pop('dose_times', [])
        stock_data = validated_data.pop('stock')
        
        # Create RegimenMedicine
        medicine = RegimenMedicine.objects.create(user=user, **medicine_data)
        
        # Create Regimen
        regimen = Regimen.objects.create(user=user, medicine=medicine, **regimen_data)
        
        # Create DoseTimes
        for dt_data in dose_times_data:
            DoseTime.objects.create(regimen=regimen, **dt_data)
        
        # Create Stock
        Stock.objects.create(regimen=regimen, **stock_data)
        
        return regimen
