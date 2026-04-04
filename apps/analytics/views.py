from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from apps.testing.models import Test
from apps.evaluation.models import TestAttempt, QuestionResponse
from apps.classroom.models import Membership

class GroupResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_release_status(self, test):
        now = timezone.now()
        # Rule 3: Open Test
        if not test.start_time and not test.deadline:
            return True, "Published"
        
        # Rule 2: Deadline Test (Release at Deadline + 12 hours)
        if test.deadline:
            release_time = test.deadline + timedelta(hours=12)
            if now < release_time:
                return False, f"Results available at {release_time.strftime('%I:%M %p, %d %b')}"
            return True, "Published"

        # Rule 1: Scheduled Test (Release ~10s after duration ends)
        if test.start_time:
            duration = test.total_duration or 0
            end_window = test.start_time + timedelta(minutes=duration) + timedelta(seconds=10)
            if now < end_window:
                return False, "Processing results..."
            return True, "Published"
            
        return False, "Pending"

    def get(self, request, group_id):
        """Returns list of tests for a group with user's score if published"""
        tests = Test.objects.filter(group_id=group_id, is_published=True)
        response_data = []

        for t in tests:
            is_released, message = self.get_release_status(t)
            attempt = TestAttempt.objects.filter(test=t, student=request.user).first()
            
            response_data.append({
                "test_id": str(t.id),
                "title": t.title,
                "is_released": is_released,
                "release_message": message,
                "my_score": float(attempt.total_score) if (attempt and is_released) else None,
                "status": attempt.status if attempt else "NOT_ATTEMPTED"
            })
        return Response(response_data)

class TestPaperView(APIView):
    """The Read-Only Paper View"""
    permission_classes = [IsAuthenticated]

    def get(self, request, test_id):
        test = get_object_or_404(Test, id=test_id)
        is_teacher = (test.group.teacher == request.user)
        
        # If teacher, they can pass ?student_id=X in the URL
        target_user = request.user
        if is_teacher and request.query_params.get('student_id'):
            target_user = get_object_or_404(Membership, group=test.group, user_id=request.query_params.get('student_id')).user

        attempt = get_object_or_404(TestAttempt, test=test, student=target_user)
        
        # Security Gate for students
        if not is_teacher:
            is_released, _ = GroupResultsView().get_release_status(test)
            if not is_released:
                return Response({"error": "Results not yet released"}, status=403)

        responses = QuestionResponse.objects.filter(attempt=attempt).select_related('question')
        
        paper = []
        for r in responses:
            q = r.question
            data = {
                "question_text": q.text,
                "type": q.question_type,
                "marks_earned": float(r.marks_earned),
                "max_marks": float(q.marks),
                "submitted": r.submitted_answer,
                "is_correct": r.is_correct,
            }

            if q.question_type == 'MCQ':
                data["options"] = list(q.options.values('id', 'text', 'is_correct'))
            elif q.question_type == 'NUMERICAL':
                data["correct_answer"] = q.correct_numerical
            elif q.question_type == 'CODE':
                # No counts, just the final status
                data["all_test_cases_passed"] = r.is_correct
                data["error_log"] = r.compilation_status # Shows if it crashed/timed out

            paper.append(data)

        return Response({
            "student_name": f"{target_user.first_name} {target_user.last_name}",
            "total_score": float(attempt.total_score),
            "questions": paper
        })
    

class TestStudentSummaryView(APIView):
    """Teacher only: Lists all students in the group and their status for a specific test"""
    permission_classes = [IsAuthenticated]

    def get(self, request, test_id):
        test = get_object_or_404(Test, id=test_id)
        
        # Security: Only the teacher who owns the group can see the full list
        if test.group.teacher != request.user:
            return Response({"error": "Unauthorized"}, status=403)

        # 1. Get all approved members of the group
        members = Membership.objects.filter(
            group=test.group, 
            status='APPROVED'
        ).select_related('user')

        # 2. Get all attempts for this specific test
        attempts = TestAttempt.objects.filter(test=test).select_related('student')
        attempt_map = {a.student_id: a for a in attempts}

        summary = []
        for member in members:
            u = member.user
            attempt = attempt_map.get(u.id)
            
            summary.append({
                "student_id": u.id,
                "name": f"{u.first_name} {u.last_name}",
                "email": u.email,
                "status": attempt.status if attempt else "ABSENT",
                "score": float(attempt.total_score) if attempt else 0.0,
                "warning_count": attempt.warning_count if attempt else 0,
                "finished_at": attempt.end_time if attempt else None
            })

        return Response({
            "test_title": test.title,
            "total_marks": float(test.total_marks),
            "students": summary
        })