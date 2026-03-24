from rest_framework import serializers
from .models import User

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'role']

    def create(self, validated_data):
        email = validated_data['email']
        initial_username = email.split('@')[0]

        user = User.objects.create_user(
            email=email,
            username=initial_username,
            password=validated_data['password'],
            role=validated_data['role'],
            is_active=True,
            is_verified=False
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'is_verified']