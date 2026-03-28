from rest_framework import viewsets, status, response, decorators
from rest_framework.exceptions import PermissionDenied
from .models import Test, Question, Topic
from .serializers import TestSerializer, QuestionSerializer, TopicSerializer
from apps.classroom.models import Group
from django.db.models import Sum

class TestViewSet(viewsets.ModelViewSet):
    serializer_class = TestSerializer

    def get_queryset(self):
        user = self.request.user
        group_id = self.request.query_params.get('group')
        if user.role == 'TEACHER':
            queryset = Test.objects.filter(group__teacher=user)
        else:
            queryset = Test.objects.filter(group__memberships__user=user, group__memberships__status='APPROVED', is_published=True)
        
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        return queryset.distinct()

    def perform_create(self, serializer):
        # Ensure students can't POST a test to any group
        group = serializer.validated_data.get('group')
        if group.teacher != self.request.user:
            raise PermissionDenied("Only the group teacher can create tests.")
        serializer.save()

    def perform_destroy(self, instance):
        # 1. Check Ownership: Ensure the teacher deleting the test is the owner of the group
        if instance.group.teacher != self.request.user:
            raise PermissionDenied("You do not have permission to delete this test.")
        
        # 2. Logic: Perform the actual deletion
        # (This will automatically trigger CASCADE deletes for all Questions, Options, etc.)
        instance.delete()
    
    @decorators.action(detail=True, methods=['post'])
    def add_question(self, request, pk=None):
        test = self.get_object()
        if test.group.teacher != request.user:
            return response.Response({"error": "Unauthorized"}, status=403)
            
        serializer = QuestionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(test=test) 
            self._sync_total_marks(test) # Keep marks updated
            return response.Response(serializer.data, status=201)
        return response.Response(serializer.errors, status=400)
    
    def perform_update(self, serializer):
        instance = serializer.save()
        self._sync_total_marks(instance)

    def _sync_total_marks(self, test):
        result = test.questions.aggregate(total=Sum('marks'))
        test.total_marks = result['total'] or 0.0
        test.save()



class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer

    def get_queryset(self):
        return Question.objects.filter(test__group__teacher=self.request.user)

    def _sync_test_marks(self, test):
        """Helper to keep the Test total_marks in sync with its Questions."""
        result = test.questions.aggregate(total=Sum('marks'))
        test.total_marks = result['total'] or 0.0
        test.save()

    def perform_create(self, serializer):
        # Trigger sync when a question is created via POST /api/testing/questions/
        instance = serializer.save()
        self._sync_test_marks(instance.test)

    def perform_update(self, serializer):
        if serializer.instance.test.is_published:
            raise PermissionDenied("Cannot edit questions of a published test.")
        
        instance = serializer.save()
        # Trigger sync when marks or question details are updated
        self._sync_test_marks(instance.test)

    def perform_destroy(self, instance):
        test = instance.test
        if test.is_published:
            raise PermissionDenied("Cannot delete questions from a published test.")
        
        instance.delete()
        # Trigger sync after a question is removed
        self._sync_test_marks(test)

# class TopicViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = Topic.objects.all()
#     serializer_class = TopicSerializer
    
#     def get_queryset(self):
#         query = self.request.query_params.get('q', None)
#         if query:
#             return Topic.objects.filter(name__icontains=query)
#         return super().get_queryset()

class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TopicSerializer
    
    def get_queryset(self):
        queryset = Topic.objects.all()
        query = self.request.query_params.get('q', None)
        group_id = self.request.query_params.get('group', None)

        # If a group ID is provided, only show topics used in that group's tests
        if group_id:
            queryset = queryset.filter(question__test__group_id=group_id).distinct()

        if query:
            queryset = queryset.filter(name__icontains=query)
            
        return queryset