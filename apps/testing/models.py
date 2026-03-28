import uuid
from django.db import models
from django.conf import settings
from apps.classroom.models import Group

class Topic(models.Model):
    """Stores reusable topics like 'Kinematics' or 'Trees'."""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Test(models.Model):
    class TimerType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'Per Question'
        TOTAL = 'TOTAL', 'Total Test Time'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='tests')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Settings
    timer_type = models.CharField(max_length=15, choices=TimerType.choices, default=TimerType.TOTAL)
    total_duration = models.PositiveIntegerField(null=True, blank=True, help_text="Duration in minutes")
    shuffle_enabled = models.BooleanField(default=False)
    
    # Schedule: If start_time is null, it is 'Free'/Always open until deadline
    start_time = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.group.name})"

class Question(models.Model):
    class QType(models.TextChoices):
        MCQ = 'MCQ', 'Multiple Choice'
        NUMERICAL = 'NUMERICAL', 'Numerical'
        CODE = 'CODE', 'Coding'

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    serial_no = models.PositiveIntegerField()
    text = models.TextField(help_text="The question text")
    question_type = models.CharField(max_length=10, choices=QType.choices)
    topics = models.ManyToManyField(Topic, blank=True)
    
    # Scoring
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=4.0)
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    
    # Used only if Test.timer_type == INDIVIDUAL
    individual_time_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Seconds")
    
    # For Numerical Answers
    correct_numerical = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['serial_no']
        unique_together = ('test', 'serial_no')

class QuestionImage(models.Model):
    """Allows multiple images per question via ImageKit URLs."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField()
    file_id = models.CharField(max_length=100, blank=True) # Useful for deleting from ImageKit later

class MCQOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

class CodeTestCase(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_cases')
    input_data = models.TextField()
    expected_output = models.TextField()
    is_hidden = models.BooleanField(default=True)