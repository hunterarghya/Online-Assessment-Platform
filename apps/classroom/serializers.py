from rest_framework import serializers
from .models import Group, Membership
from apps.users.serializers import UserSerializer

class MembershipSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = Membership
        fields = ['id', 'user_details', 'status', 'joined_at']

class GroupSerializer(serializers.ModelSerializer):
    teacher_name = serializers.ReadOnlyField(source='teacher.email')
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'teacher_name', 'invite_code', 'member_count', 'created_at']

    def get_member_count(self, obj):
        return obj.memberships.filter(status=Membership.Status.APPROVED).count()