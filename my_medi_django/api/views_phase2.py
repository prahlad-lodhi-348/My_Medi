from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from math import floor

from .models import (
    Regimen, RegimenMedicine, DoseTime, Stock, IntakeLog
)
from .serializers_phase2 import (
    RegimenWizardSerializer, RegimenReadSerializer, RegimenCreateSerializer,
    IntakeUpsertSerializer, StockPatchSerializer, StockRestockSerializer,
    StockReorderResponseSerializer
)
from .timezone_utils import get_request_tz


def compute_avg_daily_required(regimen):
    """
    Compute average daily required quantity for a regimen.
    Based on dose_times and their days_of_week.
    """
    dose_times = regimen.dose_times.all()
    if not dose_times.exists():
        return Decimal('0')

    total_weekly = Decimal('0')
    for dt in dose_times:
        days = dt.days_of_week if dt.days_of_week else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekly_count = len(days)
        total_weekly += dt.quantity * weekly_count

    return total_weekly / Decimal('7')


class RegimenWizardView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Create a complete regimen with medicine, dose_times, and stock in one transaction."""
        print("REQUEST DATA :", request.data)
        serializer = RegimenWizardSerializer(
            data=request.data,
            context={'user': request.user}
        )
        if serializer.is_valid():
            regimen = serializer.save()
            response_serializer = RegimenReadSerializer(regimen)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegimenListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all regimens for the user."""
        regimens = Regimen.objects.filter(user=request.user)
        serializer = RegimenReadSerializer(regimens, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Create a new regimen (without medicine and stock)."""
        serializer = RegimenCreateSerializer(data=request.data)
        if serializer.is_valid():
            regimen = serializer.save(user=request.user)
            response_serializer = RegimenReadSerializer(regimen)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegimenDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_regimen(self, pk, user):
        try:
            return Regimen.objects.get(id=pk, user=user)
        except Regimen.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get a specific regimen."""
        regimen = self.get_regimen(pk, request.user)
        if not regimen:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RegimenReadSerializer(regimen)
        return Response(serializer.data)

    def patch(self, request, pk):
        """Update a regimen."""
        regimen = self.get_regimen(pk, request.user)
        if not regimen:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = RegimenCreateSerializer(regimen, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            response_serializer = RegimenReadSerializer(regimen)
            return Response(response_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """Delete a regimen and its related dose_times/stock, but not the medicine if still in use."""
        regimen = self.get_regimen(pk, request.user)
        if not regimen:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        medicine = regimen.medicine
        regimen.delete()

        # Delete medicine only if no other regimens use it
        if not Regimen.objects.filter(medicine=medicine).exists():
            medicine.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class RegimenCalendarView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, regimen_id):
        """Get calendar view for intake logs."""
        try:
            regimen = Regimen.objects.get(id=regimen_id, user=request.user)
        except Regimen.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        tz = get_request_tz(request)

        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else date.today()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else date.today()
        except (ValueError, TypeError):
            return Response({'detail': 'Invalid date format (use YYYY-MM-DD)'}, status=status.HTTP_400_BAD_REQUEST)

        dose_times = regimen.dose_times.all()
        intake_logs = IntakeLog.objects.filter(
            regimen=regimen,
            date__gte=start_date,
            date__lte=end_date
        )

        calendar = {}
        current_date = start_date

        while current_date <= end_date:
            day_name = current_date.strftime('%a')
            calendar[current_date.isoformat()] = {
                'day': day_name,
                'doses': []
            }

            for dose_time in dose_times:
                days_of_week = dose_time.days_of_week or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                if day_name in days_of_week or day_name[:3] in days_of_week:
                    log = intake_logs.filter(dose_time=dose_time, date=current_date).first()

                    scheduled_dt = datetime.combine(current_date, dose_time.time)
                    scheduled_local = scheduled_dt.replace(tzinfo=tz)
                    now = timezone.now()

                    if log:
                        status_val = log.status
                    else:
                        if scheduled_local < now:
                            status_val = 'MISSED'
                        else:
                            status_val = 'PENDING'

                    calendar[current_date.isoformat()]['doses'].append({
                        'dose_time_id': dose_time.id,
                        'time': dose_time.time.isoformat(),
                        'quantity': str(dose_time.quantity),
                        'unit': dose_time.unit,
                        'label': dose_time.label,
                        'status': status_val,
                        'scheduled_local': scheduled_local.isoformat() if scheduled_local.tzinfo else scheduled_dt.isoformat(),
                    })

            current_date += timedelta(days=1)

        return Response(calendar)


class IntakeUpsertView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        """Upsert an intake log and update stock."""
        serializer = IntakeUpsertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        regimen = serializer.validated_data.get('regimen')
        dose_time = serializer.validated_data.get('dose_time')

        # Security: ensure regimen belongs to user
        if regimen.user != request.user:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        # Validate dose_time belongs to regimen
        if dose_time.regimen != regimen:
            return Response({'detail': 'Invalid dose_time'}, status=status.HTTP_400_BAD_REQUEST)

        new_status = serializer.validated_data.get('status')
        intake_date = serializer.validated_data.get('date')

        intake_log, created = IntakeLog.objects.select_for_update().get_or_create(
            regimen=regimen,
            dose_time=dose_time,
            date=intake_date,
            user=request.user,
            defaults={
                'status': new_status,
                'taken_at': timezone.now() if new_status == 'TAKEN' else None,
                'quantity': serializer.validated_data.get('quantity'),
                'unit': serializer.validated_data.get('unit'),
            }
        )

        old_status = None
        if not created:
            old_status = intake_log.status
            intake_log.status = new_status
            intake_log.taken_at = timezone.now() if new_status == 'TAKEN' else None
            intake_log.save()

        stock = Stock.objects.select_for_update().get(regimen=regimen)
        quantity_change = dose_time.quantity

        # Clean stock logic
        if new_status == 'TAKEN' and old_status != 'TAKEN':
            if stock.current_quantity < quantity_change:
                return Response({'detail': 'INSUFFICIENT_STOCK'}, status=status.HTTP_400_BAD_REQUEST)
            stock.current_quantity -= quantity_change

        elif old_status == 'TAKEN' and new_status != 'TAKEN':
            stock.current_quantity += quantity_change

        stock.save()

        response_serializer = IntakeUpsertSerializer(intake_log)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class StockStatusView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, regimen_id):
        """Get stock status for a regimen."""
        try:
            regimen = Regimen.objects.get(id=regimen_id, user=request.user)
            stock = Stock.objects.get(regimen=regimen)
        except (Regimen.DoesNotExist, Stock.DoesNotExist):
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        avg_daily = compute_avg_daily_required(regimen)

        estimated_out = None
        if avg_daily > 0:
            days_remaining = stock.current_quantity / avg_daily
            estimated_out = date.today() + timedelta(days=int(floor(float(days_remaining))))
        else:
            days_remaining = Decimal('0')

        return Response({
            'current_quantity': str(stock.current_quantity),
            'unit': stock.unit,
            'avg_daily_required': str(avg_daily),
            'days_remaining': str(days_remaining),
            'estimated_out_of_stock_date': estimated_out.isoformat() if estimated_out else None,
            'is_low_stock': days_remaining <= stock.low_stock_threshold_days,
            'low_stock_threshold_days': stock.low_stock_threshold_days,
            'reorder_url': stock.reorder_url,
            'last_low_stock_seen_at': stock.last_low_stock_seen_at,
            'last_reorder_response': stock.last_reorder_response,
            'last_reorder_response_at': stock.last_reorder_response_at,
        })


class StockUpdateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, regimen_id):
        """Update stock parameters."""
        try:
            regimen = Regimen.objects.get(id=regimen_id, user=request.user)
            stock = Stock.objects.get(regimen=regimen)
        except (Regimen.DoesNotExist, Stock.DoesNotExist):
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StockPatchSerializer(stock, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StockRestockView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, regimen_id):
        """Add quantity to stock."""
        try:
            regimen = Regimen.objects.get(id=regimen_id, user=request.user)
            stock = Stock.objects.get(regimen=regimen)
        except (Regimen.DoesNotExist, Stock.DoesNotExist):
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StockRestockSerializer(data=request.data)
        if serializer.is_valid():
            add_quantity = serializer.validated_data['add_quantity']
            stock.current_quantity += add_quantity
            stock.save()
            return Response({
                'current_quantity': str(stock.current_quantity),
                'unit': stock.unit,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StockReorderResponseView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, regimen_id):
        """Record reorder response."""
        try:
            regimen = Regimen.objects.get(id=regimen_id, user=request.user)
            stock = Stock.objects.get(regimen=regimen)
        except (Regimen.DoesNotExist, Stock.DoesNotExist):
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = StockReorderResponseSerializer(data=request.data)
        if serializer.is_valid():
            ordered = serializer.validated_data['ordered']
            stock.last_reorder_response = 'YES' if ordered else 'NO'
            stock.last_reorder_response_at = timezone.now()
            stock.save()
            return Response({
                'last_reorder_response': stock.last_reorder_response,
                'last_reorder_response_at': stock.last_reorder_response_at,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LowStockAlertsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get all regimens with low stock."""
        regimens = Regimen.objects.filter(user=request.user, is_active=True)
        low_stock_regimens = []

        for regimen in regimens:
            try:
                stock = Stock.objects.get(regimen=regimen)
                avg_daily = compute_avg_daily_required(regimen)
                if avg_daily > 0:
                    days_remaining = stock.current_quantity / avg_daily
                    if days_remaining <= stock.low_stock_threshold_days:
                        estimated_out = date.today() + timedelta(
                            days=int(floor(float(days_remaining)))
                        )
                        low_stock_regimens.append({
                            'regimen_id': regimen.id,
                            'medicine_name': regimen.medicine.name,
                            'current_quantity': str(stock.current_quantity),
                            'unit': stock.unit,
                            'avg_daily_required': str(avg_daily),
                            'days_remaining': str(days_remaining),
                            'estimated_out_of_stock_date': estimated_out.isoformat(),
                            'low_stock_threshold_days': stock.low_stock_threshold_days,
                            'reorder_url': stock.reorder_url,
                        })
            except Stock.DoesNotExist:
                pass

        return Response(low_stock_regimens)


class MedicineInventoryView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get aggregated inventory for all medicines across regimens."""
        medicines = RegimenMedicine.objects.filter(user=request.user)

        data = []

        for medicine in medicines:
            regimens = Regimen.objects.filter(
                user=request.user,
                medicine=medicine
            )

            total_stock = Decimal('0')
            total_avg_daily = Decimal('0')
            is_low_stock = False

            for regimen in regimens:
                try:
                    stock = Stock.objects.get(regimen=regimen)
                    total_stock += stock.current_quantity

                    avg = compute_avg_daily_required(regimen)
                    total_avg_daily += avg

                    if avg > 0:
                        days_rem = stock.current_quantity / avg
                        if days_rem <= stock.low_stock_threshold_days:
                            is_low_stock = True

                except Stock.DoesNotExist:
                    continue

            if total_avg_daily > 0:
                days_remaining = total_stock / total_avg_daily
                estimated_out = date.today() + timedelta(
                    days=int(floor(float(days_remaining)))
                )
            else:
                days_remaining = Decimal('0')
                estimated_out = None

            data.append({
                'medicine_id': medicine.id,
                'name': medicine.name,
                'form': medicine.form,
                'strength': medicine.strength,
                'total_stock': str(total_stock),
                'avg_daily_required': str(total_avg_daily),
                'days_remaining': str(days_remaining),
                'estimated_out_of_stock_date': estimated_out.isoformat() if estimated_out else None,
                'is_low_stock': is_low_stock,
            })

        return Response(data)

