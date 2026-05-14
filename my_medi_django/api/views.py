from django.contrib.auth import get_user_model
from .serializers import ResendVerificationSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from django.shortcuts import render, redirect
from .serializers import RegisterSerializer, LoginSerializer, ProfileSerializer, MedicineSerializer
from .models import User, Medicine, Profile
from .utils import send_verification_email
from django.urls import reverse
from django.conf import settings
import google.generativeai as genai
import json
import base64
from rest_framework.parsers import MultiPartParser, FormParser
from PIL import Image
import io
from urllib.parse import urlencode


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
        success = False
        try:
            user = User.objects.get(email_verification_token=token, is_email_verified=False)
            user.is_email_verified = True
            user.email_verification_token = None
            user.save()
            success = True
        except User.DoesNotExist:
            success = False

        # अगर आपके पास web frontend URL है तो redirect कर दो
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "").strip()
        if frontend_base:
            params = urlencode({"verified": "1" if success else "0"})
            return redirect(f"{frontend_base}/signin?{params}")

        # वरना simple HTML page दिखा दो (no frontend)
        if success:
            return HttpResponse(
                "<h2>Email verified ✅</h2><p>Now you can go back to the app and sign in.</p>",
                content_type="text/html",
            )
        return HttpResponse(
            "<h2>Invalid / expired link</h2><p>Please request a new verification email.</p>",
            content_type="text/html",
            status=400,
        )

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip()
        password = serializer.validated_data["password"]

        # Step 1: email se user dhundo
        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Django authenticate (username chahiye internally)
        user = authenticate(username=user_obj.username, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 3: Email verified check
        if not user.is_email_verified:
            return Response(
                {"error": "Email not verified."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 4: Token do
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
        profile, created = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile)
        return Response(serializer.data)

class AnalyzeMedicineView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        text_input = request.data.get('text', '')
        image_file = request.FILES.get('image')

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = """You are a medicine analysis expert. Analyze this medicine/image and respond with ONLY valid JSON parsable by json.loads(). Use exactly these keys: {"how_it_works": "2 simple sentences", "side_effects": "bullet points as string", "safety_advice": "safety precautions as string"}. No other text, explanations, or markdown."""

        if image_file:
            image = Image.open(io.BytesIO(image_file.read()))
            response = model.generate_content([prompt, image])
        else:
            response = model.generate_content(prompt + "\n\nMedicine info: " + text_input)

        def extract_clean_json(text):
            import re
            # Extract JSON from ```json ... ```
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = re.sub(r'^.*?(\{.*\}).*?$', r'\1', text, flags=re.DOTALL).strip()
            try:
                return json.loads(json_str)
            except:
                raise ValueError("Invalid JSON")

        try:
            ai_data = extract_clean_json(response.text)
            return Response({
                'how_it_works': ai_data.get('how_it_works', 'Information not available'),
                'side_effects': ai_data.get('side_effects', 'Information not available'),
                'safety_advice': ai_data.get('safety_advice', 'Information not available')
            })
        except ValueError:
            return Response({'error': 'AI analysis failed - invalid JSON format', 'raw': response.text}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

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
        dosage = request.data.get('dosage')
        frequency = request.data.get('frequency')
        notes = request.data.get('notes', '')
        image_file = request.FILES.get('image')

        # AI Analysis if image provided
        working_mechanism = 'Information not available'
        side_effects = 'Information not available'
        if image_file:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            image = genai.upload_file(image_file)
            prompt = """Identify this medicine and provide: 1. How it works (simple 2 sentences), 2. Potential side effects (bullet points), 3. Safety precautions. Format it as clean JSON."""
            response = model.generate_content([prompt, image])
            try:
                ai_data = json.loads(response.text)
                working_mechanism = ai_data.get('how_it_works', 'Information not available')
                side_effects = ai_data.get('side_effects', 'Information not available')
            except:
                pass

        medicine, created = Medicine.objects.get_or_create(
            user=request.user,
            name=name,
            defaults={'dosage': dosage, 'frequency': frequency, 'notes': notes, 'working_mechanism': working_mechanism, 'side_effects': side_effects}
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Generate ONE personalized health tip based on recent health data (steps: {data['step_count']}, water: {data['water_intake']}ml) and these medications: {json.dumps(data['medicines'])}. Keep concise, actionable, 1 sentence."
        response = model.generate_content(prompt)
        tip = response.text.strip()
        return Response({'tip': tip})

class AIChatView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get('message')
        if not message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """\nYou are a helpful medical AI assistant.\nProvide safe, general health guidance.\nDo NOT provide diagnosis.\nSuggest consulting a doctor if symptoms are serious.\n\nUser question: {}""".format(message)
        
        try:
            response = model.generate_content(prompt)
            ai_text = response.text.strip()
            return Response({'response': ai_text})
        except Exception:
            return Response(
                {'error': 'AI service unavailable'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


def register(request):
    serializer = YourSerializer(data=request.data)
    
    if serializer.is_valid():
        serializer.save()
        return Response({"msg": "User created"})
    
    print(serializer.errors)   # 👈 terminal me error dikhega
    return Response(serializer.errors, status=400)


def home(request):
    if not request.user.is_authenticated:
        return redirect('/admin/login/')
    medicines = Medicine.objects.filter(user=request.user)
    return render(request, 'home.html', {'user': request.user, 'medicines': medicines})





UserModel = get_user_model()

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

        return Response(
            {"message": "If this email is registered and not verified, a verification link has been sent."},
            status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.auth:
            request.auth.delete()
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)