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
from django.conf import settings
from imagekitio import ImageKit


# 2. Use this specific setup for Version 5.2.0
imagekit = ImageKit(
    private_key=settings.IMAGEKIT_PRIVATE_KEY,
    public_key=settings.IMAGEKIT_PUBLIC_KEY,
    url_endpoint=settings.IMAGEKIT_URL_ENDPOINT
)


# imagekit = ImageKit(
#     settings.IMAGEKIT_PRIVATE_KEY,
#     settings.IMAGEKIT_PUBLIC_KEY,
#     settings.IMAGEKIT_URL_ENDPOINT
# )

# apps/users/views.py



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
            User.objects.filter(email=email).update(is_verified=True)
            return Response({"message": "Verified"})

        return Response({"error": "Invalid OTP"}, status=400)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        required_role = request.data.get("role")

        user_obj = User.objects.filter(email=email, role=required_role).first()

        if not user_obj:
            return Response({"error": "Account not found for this role"}, status=401)

        user = authenticate(username=user_obj.username, password=password)

        if not user:
            return Response({"error": "Invalid credentials"}, status=401)
        
        # if user.role != required_role:
        #     return Response({"error": f"This account is not registered as a {required_role.lower()}."}, status=403)

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


# class ResetPasswordView(APIView):
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         email = request.data.get("email")
#         otp = request.data.get("otp")
#         new_password = request.data.get("password")

#         if verify_otp(email, otp):
#             user = User.objects.get(email=email)
#             user.set_password(new_password)
#             user.save()
#             return Response({"message": "Password reset successful"})

#         return Response({"error": "Invalid OTP"}, status=400)

class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("password")

        if verify_otp(email, otp):
            # 1. Find all accounts linked to this email
            users = User.objects.filter(email=email)
            
            if not users.exists():
                return Response({"error": "User not found"}, status=404)

            # 2. Update the password for every account found
            for user in users:
                user.set_password(new_password)
                user.save()
                
            return Response({"message": "Password reset successful for all roles associated with this email."})

        return Response({"error": "Invalid OTP"}, status=400)
    
class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        role = request.GET.get('role', 'STUDENT')
        redirect_uri = request.build_absolute_uri(reverse('google_callback'))
        request.session['auth_role'] = role
        return oauth.google.authorize_redirect(request, redirect_uri)



class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        role = request.session.get('auth_role', 'STUDENT') # Retrieve the role
        # 1. Exchange the code for a token
        token = oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        email = user_info['email']

        # Look for a user with this specific email AND role
        user = User.objects.filter(email=email, role=role).first()

        if not user:
            # Create a new user account for this specific role
            user = User.objects.create_user(
                email=email,
                username=f"{email.split('@')[0]}_{role.lower()}",
                role=role,
                is_verified=True
            )

        

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
    

class ImageKitAuthView(APIView):
    """
    Provides security signatures for client-side uploads to ImageKit.
    Only authenticated teachers should ideally be able to upload.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Optional: Check if the user is a teacher
        if request.user.role != 'TEACHER':
            return Response({"error": "Only teachers can upload images"}, status=403)
            
        try:
            auth_params = imagekit.get_authentication_parameters()
            # auth_params already contains {'token': ..., 'signature': ..., 'expire': ...}
            return Response(auth_params)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

