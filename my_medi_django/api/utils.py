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