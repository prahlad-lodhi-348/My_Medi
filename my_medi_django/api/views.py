from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import authenticate

import json
import io
from PIL import Image
import google.generativeai as genai

from .serializers import (
    RegisterSerializer, LoginSerializer, ProfileSerializer,
    MedicineSerializer, ResendVerificationSerializer
)
from .models import User, Medicine, Profile, Regimen, Stock, IntakeLog
from .utils import send_verification_email
from decimal import Decimal

UserModel = get_user_model()


def home(request):
    if not request.user.is_authenticated:
        return redirect('/admin/login/')
    medicines = Medicine.objects.filter(user=request.user)
    return render(request, 'home.html', {'user': request.user, 'medicines': medicines})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            send_verification_email(user, request)
            return Response({'message': 'User registered. Check email for verification.'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            user = User.objects.get(email_verification_token=token, is_email_verified=False)
            user.is_email_verified = True
            user.email_verification_token = None
            user.save()
            return Response({'message': 'Email verified successfully.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'Invalid or already used token.'}, status=status.HTTP_400_BAD_REQUEST)


class VerifyEmailWebView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        context = {}
        try:
            user = User.objects.get(email_verification_token=token, is_email_verified=False)
            user.is_email_verified = True
            user.email_verification_token = None
            user.save()
            context = {'success': True, 'user': user}
        except User.DoesNotExist:
            context = {'success': False, 'error': 'Invalid or already used token.'}
        return render(request, 'email_verified.html', context)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        password = serializer.validated_data["password"]

        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=user_obj.username, password=password)
        if not user:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_email_verified:
            return Response({"error": "Email not verified."}, status=status.HTTP_403_FORBIDDEN)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "username": user.username,
            "email": user.email,
            "is_email_verified": True
        }, status=status.HTTP_200_OK)


class ProfileView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AnalyzeMedicineView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        text_input = request.data.get('text', '')
        image_file = request.FILES.get('image')

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = """You are a medicine analysis expert. Analyze this medicine/image and respond with ONLY valid JSON. Use exactly these keys: {"how_it_works": "2 simple sentences", "side_effects": "bullet points as string", "safety_advice": "safety precautions as string"}. No other text."""

        try:
            if image_file:
                image = Image.open(io.BytesIO(image_file.read()))
                response = model.generate_content([prompt, image])
            else:
                response = model.generate_content(prompt + "\n\nMedicine info: " + text_input)

            def extract_clean_json(text):
                import re
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = re.sub(r'^.*?(\{.*\}).*?$', r'\1', text, flags=re.DOTALL).strip()
                return json.loads(json_str)

            ai_data = extract_clean_json(response.text)
            return Response({
                'how_it_works': ai_data.get('how_it_works', 'Information not available'),
                'side_effects': ai_data.get('side_effects', 'Information not available'),
                'safety_advice': ai_data.get('safety_advice', 'Information not available')
            })
        except Exception as e:
            return Response({'error': 'AI analysis failed', 'details': str(e)[:100]}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


class MedicineListCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        medicines = Medicine.objects.filter(user=request.user)
        serializer = MedicineSerializer(medicines, many=True)
        return Response(serializer.data)

    def post(self, request):
        name = request.data.get('name')
        if not name:
            return Response({'error': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        dosage = request.data.get('dosage') or None
        frequency = request.data.get('frequency') or None
        notes = request.data.get('notes', '') or ''
        image_file = request.FILES.get('image')

        working_mechanism = 'Information not available'
        side_effects = 'Information not available'
        
        if image_file:
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-2.5-flash')
                image = genai.upload_file(image_file)
                prompt = """Identify this medicine: 1. How it works, 2. Side effects, 3. Safety. Format as clean JSON."""
                response = model.generate_content([prompt, image])
                try:
                    ai_data = json.loads(response.text)
                    working_mechanism = ai_data.get('how_it_works', 'Information not available')
                    side_effects = ai_data.get('side_effects', 'Information not available')
                except:
                    pass
            except:
                pass

        medicine, created = Medicine.objects.get_or_create(
            user=request.user,
            name=name,
            defaults={
                'dosage': dosage,
                'frequency': frequency,
                'notes': notes,
                'working_mechanism': working_mechanism,
                'side_effects': side_effects
            }
        )

        serializer = MedicineSerializer(medicine)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReminderSpeechView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, med_id):
        try:
            med = Medicine.objects.get(id=med_id, user=request.user)
            message = f"Hello {request.user.username}, it's time for {med.name}. This helps with {med.working_mechanism}. Don't forget to take it and mark as taken!"
            return Response({'speech': message})
        except Medicine.DoesNotExist:
            return Response({'error': 'Medicine not found'}, status=status.HTTP_404_NOT_FOUND)


class AIInsightsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, created = Profile.objects.get_or_create(user=request.user)
        medicines = Medicine.objects.filter(user=request.user).order_by('-created_at')[:5]
        data = {
            'step_count': profile.step_count,
            'water_intake': profile.water_intake,
            'medicines': [{'name': m.name, 'dosage': m.dosage, 'frequency': m.frequency, 'side_effects': m.side_effects} for m in medicines]
        }
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Generate ONE health tip. Steps: {data['step_count']}, Water: {data['water_intake']}ml, Meds: {json.dumps(data['medicines'])}. 1 sentence."
        response = model.generate_content(prompt)
        return Response({'tip': response.text.strip()})


class AIChatView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def _build_medication_context(self, user):
        regimens = Regimen.objects.filter(user=user, is_active=True).select_related('medicine', 'stock')
        medications = []
        
        for regimen in regimens:
            medicine = regimen.medicine
            dose_times = regimen.dose_times.all().order_by('time')
            doses = [{'time': str(dt.time), 'quantity': float(dt.quantity), 'unit': dt.unit, 'days': dt.days_of_week or []} for dt in dose_times]
            
            medication = {'name': medicine.name, 'strength': medicine.strength, 'form': medicine.form, 'doses': doses}
            
            try:
                stock = regimen.stock
                medication['stock'] = {'current_quantity': float(stock.current_quantity), 'unit': stock.unit, 'low_stock_threshold_days': stock.low_stock_threshold_days}
            except Stock.DoesNotExist:
                pass
            
            from django.utils import timezone
            today = timezone.now().date()
            recent_intakes = IntakeLog.objects.filter(regimen=regimen, date=today).values('status').distinct()
            
            if recent_intakes.exists():
                medication['today_status'] = [intake['status'] for intake in recent_intakes]
            
            medications.append(medication)
        
        return {'medications': medications}

    def post(self, request):
        message = request.data.get('message')
        if not message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')

        medication_context = self._build_medication_context(request.user)
        medication_data = json.dumps(medication_context, indent=2)

        system_prompt = f"""You are a helpful medical AI assistant. Provide safe, general health guidance. Do NOT provide diagnosis. Suggest consulting a doctor if serious.

User's Medications:
{medication_data}

Use the above medication information when relevant."""

        prompt = f"User question: {message}"

        try:
            response = model.generate_content([system_prompt, prompt])
            return Response({'response': response.text.strip()})
        except Exception as e:
            error_msg = str(e)
            if '429' in error_msg or 'quota' in error_msg.lower() or 'ResourceExhausted' in error_msg:
                return Response(
                    {'error': 'AI quota exceeded. Please check your Google AI Studio billing and usage limits.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            return Response({'error': f'AI service unavailable: {error_msg[:100]}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()

        try:
            user = UserModel.objects.get(email__iexact=email)
            if not user.is_email_verified:
                send_verification_email(user, request)
        except UserModel.DoesNotExist:
            pass

        return Response({"message": "If this email is registered and not verified, a verification link has been sent."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.auth:
            request.auth.delete()
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
