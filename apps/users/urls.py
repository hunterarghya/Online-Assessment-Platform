from django.urls import path
from .views import (
    RegisterView, VerifyOTPView, LoginView,
    RequestPasswordResetView, ResetPasswordView,
    GoogleLoginView, GoogleCallbackView, UserProfileView
)


urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('verify-otp/', VerifyOTPView.as_view()),
    path('login/', LoginView.as_view()),
    path('password-reset/', RequestPasswordResetView.as_view()),
    path('reset-password/', ResetPasswordView.as_view()),
    path('google/', GoogleLoginView.as_view(), name='google_login'),
    path('google/callback/', GoogleCallbackView.as_view(), name='google_callback'),
    path('me/', UserProfileView.as_view()),
]