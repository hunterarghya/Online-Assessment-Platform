from django.db import models
from django.conf import settings
from apps.testing.models import Test, Question

class TestAttempt(models.Model):
    class Status(models.TextChoices):
        STARTED = 'STARTED', 'Started'
        COMPLETED = 'COMPLETED', 'Completed'
        AUTO_SUBMITTED = 'AUTO_SUBMITTED', 'Auto-Submitted'
        DISQUALIFIED = 'DISQUALIFIED', 'Disqualified'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='test_attempts'
    )
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='attempts')
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.STARTED
    )
    
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    
    # To detect cheating later: count tab switches
    warning_count = models.PositiveIntegerField(default=0)

    class Meta:
        # A student can attempt a specific test only once
        unique_together = ('student', 'test')

    def __str__(self):
        return f"{self.student.email} - {self.test.title}"

class QuestionResponse(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    is_marked_for_review = models.BooleanField(default=False)
    
    # We use a TextField/JSONField to store different types of answers:
    # MCQ: ID of the option | Numerical: The number | Code: The source code string
    submitted_answer = models.TextField(blank=True, null=True)
    
    is_correct = models.BooleanField(default=False)
    marks_earned = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    
    # Specific for Coding Questions
    judge0_token = models.CharField(max_length=100, blank=True, null=True)
    compilation_status = models.TextField(blank=True, null=True) # To store errors

      
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('attempt', 'question')