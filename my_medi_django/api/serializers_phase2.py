from rest_framework import serializers
from django.db import transaction
from .models import (
    RegimenMedicine,
    Regimen,
    DoseTime,
    Stock,
    IntakeLog,
)


class RegimenMedicineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimenMedicine
        fields = ['name', 'form', 'strength', 'notes']


class DoseTimeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoseTime
        fields = ['time', 'label', 'quantity', 'unit', 'days_of_week']


class StockCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ['current_quantity', 'unit', 'low_stock_threshold_days', 'reorder_url']


class RegimenCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Regimen
        fields = ['medicine', 'start_date', 'end_date', 'instructions', 'is_active']


class RegimenMedicineReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimenMedicine
        fields = ['id', 'name', 'form', 'strength', 'notes', 'created_at']


class DoseTimeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoseTime
        fields = ['id', 'time', 'label', 'quantity', 'unit', 'days_of_week']


class StockReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = [
            'current_quantity', 'unit', 'low_stock_threshold_days',
            'reorder_url', 'last_low_stock_seen_at',
            'last_reorder_response', 'last_reorder_response_at',
        ]


class RegimenReadSerializer(serializers.ModelSerializer):
    medicine = RegimenMedicineReadSerializer(read_only=True)
    dose_times = DoseTimeReadSerializer(many=True, read_only=True)
    stock = StockReadSerializer(read_only=True)

    class Meta:
        model = Regimen
        fields = [
            'id', 'medicine', 'start_date', 'end_date',
            'instructions', 'is_active', 'created_at',
            'dose_times', 'stock',
        ]


class IntakeUpsertSerializer(serializers.ModelSerializer):
    regimen = serializers.PrimaryKeyRelatedField(queryset=Regimen.objects.all())
    dose_time = serializers.PrimaryKeyRelatedField(queryset=DoseTime.objects.all())

    class Meta:
        model = IntakeLog
        fields = [
            'id', 'regimen', 'dose_time', 'date',
            'status', 'taken_at', 'quantity', 'unit',
        ]
        read_only_fields = ['id', 'taken_at']


class StockPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = [
            'current_quantity', 'unit',
            'low_stock_threshold_days', 'reorder_url',
        ]


class StockRestockSerializer(serializers.Serializer):
    add_quantity = serializers.DecimalField(max_digits=10, decimal_places=2)


class StockReorderResponseSerializer(serializers.Serializer):
    ordered = serializers.BooleanField()


class RegimenWizardSerializer(serializers.Serializer):
    medicine = RegimenMedicineCreateSerializer()
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    instructions = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)
    dose_times = DoseTimeCreateSerializer(many=True)
    stock = StockCreateSerializer()

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['user']
        medicine_data = validated_data.pop('medicine')
        dose_times_data = validated_data.pop('dose_times')
        stock_data = validated_data.pop('stock')

        medicine = RegimenMedicine.objects.create(user=user, **medicine_data)
        regimen = Regimen.objects.create(user=user, medicine=medicine, **validated_data)

        for dt_data in dose_times_data:
            DoseTime.objects.create(regimen=regimen, **dt_data)

        Stock.objects.create(regimen=regimen, **stock_data)

        return regimen

