from django.urls import path
from . import views
from .views_phase2 import (
    RegimenWizardView, RegimenListView, RegimenDetailView, RegimenCalendarView,
    IntakeUpsertView, StockStatusView, StockUpdateView, StockRestockView,
    StockReorderResponseView, LowStockAlertsView, MedicineInventoryView,
    CaregiverListCreateView, CaregiverDeleteView,
    register_caregiver_push_token, notification_log_view, trigger_weekly_report
)

app_name = 'api'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify/<str:token>/', views.VerifyEmailView.as_view(), name='verify'),
    path('verify-email/<str:token>/', views.VerifyEmailWebView.as_view(), name='verify-email-web'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('medicines/', views.MedicineListCreateView.as_view(), name='medicines'),
    path('analyze-medicine/', views.AnalyzeMedicineView.as_view(), name='analyze_medicine'),
    path('reminder-speech/<int:med_id>/', views.ReminderSpeechView.as_view(), name='reminder_speech'),
    path('ai-insights/', views.AIInsightsView.as_view(), name='ai_insights'),
    path('ai-chat/', views.AIChatView.as_view(), name='ai_chat'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Phase 2 - Regimen endpoints
    path('regimens/wizard/', RegimenWizardView.as_view(), name='regimen-wizard'),
    path('regimens/', RegimenListView.as_view(), name='regimen-list'),
    path('regimens/<int:pk>/', RegimenDetailView.as_view(), name='regimen-detail'),
    path('regimens/<int:regimen_id>/calendar/', RegimenCalendarView.as_view(), name='regimen-calendar'),

    # Phase 2 - Intake endpoints
    path('intakes/', IntakeUpsertView.as_view(), name='intakes-upsert'),

    # Phase 2 - Stock endpoints
    path('regimens/<int:regimen_id>/stock/status/', StockStatusView.as_view(), name='stock-status'),
    path('regimens/<int:regimen_id>/stock/', StockUpdateView.as_view(), name='stock-update'),
    path('regimens/<int:regimen_id>/stock/restock/', StockRestockView.as_view(), name='stock-restock'),
    path('regimens/<int:regimen_id>/stock/reorder-response/', StockReorderResponseView.as_view(), name='stock-reorder-response'),

    # Phase 2 - Alert endpoints
    path('alerts/low-stock/', LowStockAlertsView.as_view(), name='low-stock-alerts'),

    # Phase 2 - Inventory endpoint
    path('inventory/', MedicineInventoryView.as_view(), name='inventory'),

    # Phase 2 - Caregiver endpoints
    path('caregivers/', CaregiverListCreateView.as_view(), name='caregiver-list-create'),
    path('caregivers/<int:pk>/', CaregiverDeleteView.as_view(), name='caregiver-delete'),
    path('caregivers/<int:pk>/register-token/', register_caregiver_push_token, name='register-caregiver-token'),
    path('notifications/log/', notification_log_view, name='notification-log'),
    path('caregivers/send-weekly-report/', trigger_weekly_report, name='send-weekly-report'),
]

