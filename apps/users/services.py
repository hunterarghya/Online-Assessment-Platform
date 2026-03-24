import redis
import random
import os
from django.conf import settings
import smtplib
from email.mime.text import MIMEText

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
    msg = MIMEText(f"Your OTP is {otp}. Valid for 5 minutes.")
    msg["Subject"] = "Verify your account"
    msg["From"] = settings.EMAIL_HOST_USER
    msg["To"] = email

    
    try:
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        server.starttls()
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        server.sendmail(settings.EMAIL_HOST_USER, email, msg.as_string())
        server.quit()
        print(f"OTP sent successfully to {email}")
    except Exception as e:
        print(f"CRITICAL EMAIL ERROR: {e}")