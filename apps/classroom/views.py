from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Group, Membership
from .serializers import GroupSerializer, MembershipSerializer

class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'TEACHER':
            return Group.objects.filter(teacher=user)
        # Students see groups where they are APPROVED members
        return Group.objects.filter(memberships__user=user, memberships__status='APPROVED')

    def perform_create(self, serializer):
        # Automatically set the logged-in teacher as the owner
        serializer.save(teacher=self.request.user)

    # ACTION: Join a group using an invite code
    @action(detail=False, methods=['post'])
    def join_by_code(self, request):
        invite_code = request.data.get('invite_code')
        try:
            group = Group.objects.get(invite_code=invite_code)
            # Logic to prevent teachers from joining their own groups or duplicate requests
            membership, created = Membership.objects.get_or_create(user=request.user, group=group)
            if not created:
                return Response({"error": "Request already sent or member exists"}, status=400)
            return Response({"message": "Join request sent to teacher"}, status=201)
        except Group.DoesNotExist:
            return Response({"error": "Invalid invite link"}, status=404)
        
    
    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        group = self.get_object()
        memberships = group.memberships.all()
        serializer = MembershipSerializer(memberships, many=True)
        return Response(serializer.data)

    
    @action(detail=True, methods=['post'])
    def respond_to_request(self, request, pk=None):
        """
        Handles Approve, Reject, and Remove actions from the frontend.
        Matches the respond() function in dashboard.html
        """
        group = self.get_object()
        membership_id = request.data.get('membership_id')
        action_type = request.data.get('action') # 'approve' or 'reject'

        try:
            membership = group.memberships.get(id=membership_id)
            
            if action_type == 'approve':
                membership.status = 'APPROVED'
                membership.save()
                return Response({"message": "Member approved successfully"})
            else:
                # If action is 'reject' or student is being 'removed', we delete the membership
                membership.delete()
                return Response({"message": "Member removed/rejected successfully"})
                
        except Membership.DoesNotExist:
            return Response({"error": "Membership record not found"}, status=404)