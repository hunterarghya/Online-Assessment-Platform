from django.utils import timezone
from django.core.cache import cache
from django.db import models, transaction
from rest_framework import viewsets, status, decorators, response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
import json


from apps.testing.models import Test, Question, MCQOption
from apps.classroom.models import Membership
from .models import TestAttempt, QuestionResponse
from .serializers import StudentQuestionSerializer, TestAttemptSerializer

from .utils import evaluate_code_glot

class TestAttemptViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TestAttemptSerializer

    def get_queryset(self):
        return TestAttempt.objects.filter(student=self.request.user)
    
    @decorators.action(detail=True, methods=['post'], url_path='start')
    def start_test(self, request, pk=None):
        user = request.user
        try:
            test = Test.objects.get(id=pk)
        except (Test.DoesNotExist, ValidationError):
            return response.Response({"error": "Test not found"}, status=404)
            
        now = timezone.now()

        # Security & Basic Checks
        membership = Membership.objects.filter(user=user, group=test.group, status='APPROVED').first()
        if not membership or user.role != 'STUDENT':
            raise PermissionDenied("You are not authorized to take this test.")
        if not test.is_published:
            raise ValidationError("This test is not yet available.")

        attempt = TestAttempt.objects.filter(student=user, test=test).first()

        
        # Rule: Scheduled tests block entry after start_time unless a session already exists.
        if test.start_time:
            ten_mins_before = test.start_time - timezone.timedelta(minutes=10)
            
            # Case: Trying to enter before the 10-minute waiting room window
            if now < ten_mins_before:
                return response.Response(
                    {"error": f"Entry opens at {ten_mins_before.strftime('%H:%M')}."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Case: Test has started. Block entry ONLY if the user hasn't already started an attempt.
            # allow a 2-minute grace period for network/loading lag.
            grace_period = test.start_time + timezone.timedelta(minutes=2)
            if now > grace_period and not attempt:
                return response.Response(
                    {"error": "Test has already started. Late entry is blocked."}, 
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Rule: If not scheduled, check for a hard deadline
        elif test.deadline and now > test.deadline:
            return response.Response(
                {"error": "The deadline for this test has passed."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        

        # Handle Attempt Record
        if not attempt:
            attempt = TestAttempt.objects.create(
                student=user, test=test, status=TestAttempt.Status.STARTED
            )
        elif attempt.status != TestAttempt.Status.STARTED:
            return response.Response({"error": "Test already submitted."}, status=400)

        # Timer Logic
        redis_key = f"test_timer:{attempt.id}"
        end_timestamp = cache.get(redis_key)

        if not end_timestamp:
            if test.total_duration:
                duration_delta = timezone.timedelta(minutes=test.total_duration)
                if test.start_time:
                    actual_end = test.start_time + duration_delta
                else:
                    actual_end = now + duration_delta
                    if test.deadline:
                        actual_end = min(actual_end, test.deadline)
                
                end_timestamp = actual_end.timestamp()
                cache.set(redis_key, end_timestamp, timeout=(test.total_duration * 60) + 300)
            else:
                end_timestamp = 0 

        # Data Delivery
        questions = test.questions.all().order_by('serial_no', 'id') # order stability
        q_serializer = StudentQuestionSerializer(questions, many=True)

        return response.Response({
            "attempt_id": attempt.id,
            "end_time": end_timestamp,
            "server_time": now.timestamp(),
            "questions": q_serializer.data,
            "timer_type": test.timer_type,
            "title": test.title,
            "shuffle_questions": test.shuffle_enabled,
            "start_time_unix": test.start_time.timestamp() if test.start_time else None
        })



    @decorators.action(detail=True, methods=['post'], url_path='run-code')
    def run_code(self, request, pk=None):
        attempt = self.get_object()
        
        # Check if the attempt is still valid
        if attempt.status != TestAttempt.Status.STARTED:
            return response.Response({"error": "Test is no longer active."}, status=403)

        question_id = request.data.get('question_id')
        source_code = request.data.get('submitted_answer')
        

        if not source_code:
            return response.Response({"error": "No code provided."}, status=400)

        try:
            # Ensure the question belongs to this specific test
            question = Question.objects.get(id=question_id, test=attempt.test, question_type='CODE')
        except Question.DoesNotExist:
            return response.Response({"error": "Question not found or is not a coding question."}, status=404)

        # Fetch all test cases (CodeTestCase model)
        test_cases = question.test_cases.all()
        
        public_results = []
        total_passed = 0
        total_count = test_cases.count()

        lang_key = getattr(question, 'programming_language', 'python').lower()

        for tc in test_cases:
            # Execute the code using secure sandbox
            result = evaluate_code_glot(
                language_key=lang_key,
                source_code=source_code, 
                stdin_data=tc.input_data
            )

            # Clean up outputs for comparison
            actual_output = str(result.get('stdout', '')).strip()
            expected_output = str(tc.expected_output).strip()
            
            # Check if it passed
            is_passed = (not result.get('error')) and (actual_output == expected_output)
            
            if is_passed:
                total_passed += 1

            # Only reveal details for non-hidden cases
            if not tc.is_hidden:
                public_results.append({
                    "input": tc.input_data,
                    "expected": tc.expected_output,
                    "actual": actual_output if not result.get('error') else None,
                    "status": "Passed" if is_passed else "Failed",
                    "error": result.get('stderr') or result.get('error')
                })
            # Hidden cases are processed but their details are NEVER added to public_results
        
        return response.Response({
            "summary": f"{total_passed}/{total_count} test cases passed.",
            "passed_count": total_passed,
            "total_count": total_count,
            "public_details": public_results
        })
    
    
    @decorators.action(detail=True, methods=['post'], url_path='log-violation')
    def log_violation(self, request, pk=None):
        attempt = self.get_object()
        if attempt.status != TestAttempt.Status.STARTED:
            return response.Response({"status": "ignored"}, status=200)

        attempt.warning_count += 1
        
        # Rule: 2 warnings allowed, 3rd switch results in disqualification
        if attempt.warning_count >= 3:
            attempt.status = TestAttempt.Status.DISQUALIFIED
            attempt.end_time = timezone.now()
            attempt.save()
            return response.Response({
                "action": "DISQUALIFY",
                "message": "Maximum tab switches exceeded. Test terminated."
            }, status=403)
        
        attempt.save()
        return response.Response({
            "action": "WARN",
            "warnings_current": attempt.warning_count
        })


    

    @decorators.action(detail=True, methods=['post'], url_path='submit-answer')
    def submit_answer(self, request, pk=None):
        attempt = self.get_object()
        test = attempt.test
        
        # 1. Validation: Is the attempt active?
        if attempt.status == TestAttempt.Status.DISQUALIFIED:
            return response.Response({"error": "Test terminated due to violations."}, status=403)
        if attempt.status != TestAttempt.Status.STARTED:
            return response.Response({"error": "Test is already submitted or closed."}, status=400)

        # 2. Global Timer Check (Redis)
        redis_key = f"test_timer:{attempt.id}"
        end_timestamp = cache.get(redis_key)
        if end_timestamp and timezone.now().timestamp() > float(end_timestamp):
            attempt.status = TestAttempt.Status.AUTO_SUBMITTED
            attempt.end_time = timezone.now()
            attempt.save()
            return response.Response({"error": "Time limit exceeded.", "action": "AUTO_SUBMIT"}, status=403)

        question_id = request.data.get('question_id')
        submitted_answer = request.data.get('submitted_answer')

        # 3. Individual Timer Protection
        # If per-question timer is on, check if they've already touched this question
        if test.timer_type == Test.TimerType.INDIVIDUAL:
            if QuestionResponse.objects.filter(attempt=attempt, question_id=question_id).exists():
                return response.Response({"error": "Question already submitted/locked."}, status=403)

        try:
            question = Question.objects.get(id=question_id, test=test)
        except Question.DoesNotExist:
            return response.Response({"error": "Question not found."}, status=404)

        # 4. Evaluation Logic
        is_correct = False
        marks_earned = 0.0
        error_message = None

        is_empty = submitted_answer is None or str(submitted_answer).strip() in ["", "[]", "null", "None"]

        if is_empty:
            marks_earned = 0.0
            is_correct = False
        
        else:
            

            if question.question_type == 'MCQ':
                try:
                    correct_ids = set(question.options.filter(is_correct=True).values_list('id', flat=True))
                    
                    # Parse the selection
                    if isinstance(submitted_answer, list):
                        selected_ids = set(map(int, submitted_answer))
                    else:
                        parsed = json.loads(submitted_answer)
                        selected_ids = set(map(int, parsed)) if isinstance(parsed, list) else {int(parsed)}

                    # RE-CHECK: If after parsing it's still empty (e.g. user submitted "[]")
                    if not selected_ids:
                        marks_earned = 0.0
                    else:
                        wrong_selected = selected_ids - correct_ids
                        correct_selected = selected_ids & correct_ids

                        if len(wrong_selected) > 0:
                            marks_earned = -abs(float(question.negative_marks))
                            is_correct = False
                        elif len(correct_selected) == len(correct_ids):
                            marks_earned = float(question.marks)
                            is_correct = True
                        else:
                            # Partial logic
                            marks_earned = (float(question.marks) / len(correct_ids)) * len(correct_selected)
                            is_correct = False
                except Exception as e:
                    marks_earned = 0.0

            elif question.question_type == 'NUMERICAL':
                try:
                    # Robust check for empty/whitespace strings
                    if not str(submitted_answer).strip():
                        marks_earned = 0.0
                        is_correct = False
                    elif abs(float(submitted_answer) - float(question.correct_numerical)) < 0.001:
                        is_correct = True
                        marks_earned = float(question.marks)
                    else:
                        is_correct = False
                        # question.negative_marks is a positive value in the DB
                        marks_earned = -abs(float(question.negative_marks)) 
                except (TypeError, ValueError):
                    # If they type "abc" in a numerical field
                    is_correct = False
                    marks_earned = -abs(float(question.negative_marks))
                    

            
            elif question.question_type == 'CODE':
                test_cases = question.test_cases.all()
                
                all_passed = True

                
                lang_key = getattr(question, 'programming_language', 'python').lower()

                for tc in test_cases:
                    # Use the utils function
                    result = evaluate_code_glot(
                        language_key=lang_key, 
                        source_code=submitted_answer, 
                        stdin_data=tc.input_data
                    )

                    actual_output = str(result.get('stdout', '')).strip()
                    expected_output = str(tc.expected_output).strip()

                    print(f"DEBUG: Glot Output: '{actual_output}' | Expected: '{expected_output}'")

                    if result.get('error') or actual_output != expected_output:
                        all_passed = False
                        error_message = result.get('stderr') or result.get('error') or "Wrong Answer"
                        break
                
                if all_passed and test_cases.exists():
                    is_correct = True
                    marks_earned = float(question.marks)
                else:
                    is_correct = False
                    marks_earned = 0.0
        # 5. Save Response
        with transaction.atomic():
            QuestionResponse.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={
                    'submitted_answer': submitted_answer,
                    'is_correct': is_correct,
                    'marks_earned': marks_earned,
                    'compilation_status': error_message
                }
            )

        return response.Response({"status": "saved", "is_correct": is_correct})


    @decorators.action(detail=True, methods=['post'], url_path='finish-test')
    def finish_test(self, request, pk=None):
        attempt = self.get_object()
        
        if attempt.status not in [TestAttempt.Status.STARTED]:
            return response.Response({"error": "Test already finished or disqualified."}, status=400)

        # 1. Calculate Positive Marks
        # positive_total = attempt.responses.filter(is_correct=True).aggregate(
        #     total=models.Sum('marks_earned')
        # )['total'] or 0.0

        total_earned = attempt.responses.aggregate(
            total=models.Sum('marks_earned')
        )['total'] or 0.0

        # 2. Calculate Negative Marks
        # Only penalize questions where an answer was actually provided but is incorrect
        # negative_total = 0.0
        # wrong_responses = attempt.responses.filter(is_correct=False).exclude(
        #     models.Q(submitted_answer__isnull=True) | models.Q(submitted_answer="")
        # )
        
        # for resp in wrong_responses:
        #     # negative_total += float(resp.question.negative_marks)
        #     if float(resp.marks_earned) == 0.0:
        #         negative_total += float(resp.question.negative_marks)

        # 3. Finalize Attempt
        # attempt.total_score = max(0.0, float(positive_total) - negative_total)
        attempt.total_score = float(total_earned)
        attempt.status = TestAttempt.Status.COMPLETED
        attempt.end_time = timezone.now()
        attempt.save()

        # 4. Cleanup
        cache.delete(f"test_timer:{attempt.id}")

        return response.Response({
            "message": "Test submitted successfully",
            "total_score": attempt.total_score,
            "status": attempt.status
        })

