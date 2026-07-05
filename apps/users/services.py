import redis
import random
import os
from django.conf import settings
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

redis_client = redis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True
)


def generate_otp(email):
    otp = str(random.randint(100000, 999999))
    redis_client.set(f"otp:{email}", otp, ex=300)
    return otp


def verify_otp(email, otp):
    stored = redis_client.get(f"otp:{email}")
    if stored == otp:
        redis_client.delete(f"otp:{email}")
        return True
    return False


def send_otp_email(email, otp):
    """
    Send OTP using Django's email backend (configured in settings.py).
    This uses the EMAIL_BACKEND / EMAIL_HOST / EMAIL_PORT / EMAIL_USE_TLS
    settings instead of raw smtplib, which is more reliable on cloud hosts
    like Render where direct SMTP connections can be flaky or blocked.
    """
    subject = "Verify your account"
    message = f"Your OTP is {otp}. Valid for 5 minutes."
    from_email = settings.EMAIL_HOST_USER

    try:
        send_mail(
            subject,
            message,
            from_email,
            [email],
            fail_silently=False,
        )
        logger.info(f"OTP sent successfully to {email}")
    except Exception as e:
        logger.error(f"CRITICAL EMAIL ERROR for {email}: {e}", exc_info=True)