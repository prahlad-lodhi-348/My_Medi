from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify/<str:token>/', views.VerifyEmailView.as_view(), name='verify'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('medicines/', views.MedicineListCreateView.as_view(), name='medicines'),
    path('analyze-medicine/', views.AnalyzeMedicineView.as_view(), name='analyze_medicine'),
    path('reminder-speech/<int:med_id>/', views.ReminderSpeechView.as_view(), name='reminder_speech'),
    path('ai-insights/', views.AIInsightsView.as_view(), name='ai_insights'),
    path('ai-chat/', views.AIChatView.as_view(), name='ai_chat'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]
