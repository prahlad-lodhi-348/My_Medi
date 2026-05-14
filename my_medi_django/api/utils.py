# from django.core.mail import send_mail
# from django.urls import reverse
# from django.conf import settings
# import uuid

# def send_verification_email(user, request):
#     token = str(uuid.uuid4())
#     user.email_verification_token = token
#     user.save()

#     verification_url = f"http://{request.get_host()}/api/verify-email/{token}/"

#     send_mail(
#         'Verify your account',
#         f'Click to verify: {verification_url}',
#         settings.EMAIL_HOST_USER,
#         [user.email],
#         fail_silently=False,
#     )
# from django.core.mail import send_mail
# from django.conf import settings

# def send_verification_email(user, request):
#     # generates UUID + saves it in user.email_verification_token
#     token = user.generate_verification_token()

#     # must match your api/urls.py: path('verify/<...:token>/' ...)
#     verification_url = request.build_absolute_uri(f"/api/verify/{token}/")

#     send_mail(
#         subject="Verify your account",
#         message=f"Click to verify: {verification_url}",
#         from_email=settings.EMAIL_HOST_USER,
#         recipient_list=[user.email],
#         fail_silently=False,
#     )


from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone

def send_verification_email(user, request):
    token = user.generate_verification_token()

    verification_url = request.build_absolute_uri(
        reverse("api:verify", kwargs={"token": str(token)})
    )

    context = {
        "username": user.username,
        "verify_url": verification_url,
        "app_name": getattr(settings, "APP_NAME", "MyMedi"),
        "year": timezone.now().year,
    }

    subject = f"Verify your email - {context['app_name']}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER)

    text_body = render_to_string("emails/verify_email.txt", context)
    html_body = render_to_string("emails/verify_email.html", context)

    send_mail(
        subject=subject,
        message=text_body,             # plain fallback
        from_email=from_email,         # professional "From"
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_body,        # HTML email
    )