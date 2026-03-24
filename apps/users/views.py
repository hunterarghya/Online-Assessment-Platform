from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from django.shortcuts import redirect
from django.urls import reverse
from .oidc import oauth

from .models import User
from .serializers import RegisterSerializer, UserSerializer
from .services import generate_otp, verify_otp, send_otp_email

from django.http import HttpResponse
import json


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            otp = generate_otp(user.email)
            send_otp_email(user.email, otp)

            return Response({"message": "OTP sent"}, status=201)

        return Response(serializer.errors, status=400)


class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if verify_otp(email, otp):
            user = User.objects.get(email=email)
            user.is_verified = True
            user.save()
            return Response({"message": "Verified"})

        return Response({"error": "Invalid OTP"}, status=400)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(username=email, password=password)

        if not user:
            return Response({"error": "Invalid credentials"}, status=401)

        if not user.is_verified:
            return Response({"error": "Verify email first"}, status=403)

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data
        })


class RequestPasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if User.objects.filter(email=email).exists():
            otp = generate_otp(email)
            send_otp_email(email, otp)
            return Response({"message": "OTP sent"})

        return Response({"error": "User not found"}, status=404)


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("password")

        if verify_otp(email, otp):
            user = User.objects.get(email=email)
            user.set_password(new_password)
            user.save()
            return Response({"message": "Password reset successful"})

        return Response({"error": "Invalid OTP"}, status=400)
    
class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        
        redirect_uri = request.build_absolute_uri(reverse('google_callback'))
        return oauth.google.authorize_redirect(request, redirect_uri)



class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # 1. Exchange the code for a token
        token = oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        email = user_info['email']

        # 2. Get or create the user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email.split('@')[0],
                'is_verified': True,
                'role': 'STUDENT'
            }
        )
        
        # 3. If user existed but wasn't verified (email reg), verify them now
        if not user.is_verified:
            user.is_verified = True
            user.save()

        # 4. Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        user_data = UserSerializer(user).data

        
        content = f"""
        <script>
            localStorage.setItem('token', '{access_token}');
            localStorage.setItem('user', JSON.stringify({json.dumps(user_data)}));
            window.location.href = '/dashboard/';
        </script>
        """
        return HttpResponse(content)

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)