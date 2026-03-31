from rest_framework import serializers
from apps.testing.models import Test, Question, MCQOption, QuestionImage
from .models import TestAttempt, QuestionResponse

# Serializer for fetching the test without answers
class StudentOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQOption
        fields = ['id', 'text'] # NEVER include is_correct here

class StudentQuestionSerializer(serializers.ModelSerializer):
    options = StudentOptionSerializer(many=True, read_only=True)
    images = serializers.SlugRelatedField(many=True, read_only=True, slug_field='image_url')
    
    
    class Meta:
        model = Question
        fields = [
            'id', 'serial_no', 'text', 'question_type', 
            'marks', 'individual_time_limit', 'options', 'images'
        ]

class TestAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestAttempt
        fields = ['id', 'start_time', 'status', 'total_score', 'warning_count']
        read_only_fields = ['start_time', 'total_score']