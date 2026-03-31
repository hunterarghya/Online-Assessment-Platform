from rest_framework import serializers
from .models import Test, Question, Topic, MCQOption, QuestionImage, CodeTestCase
from django.utils import timezone


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ['id', 'name']

class QuestionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionImage
        fields = ['id', 'image_url']

class MCQOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQOption
        fields = ['id', 'text', 'is_correct']

class CodeTestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodeTestCase
        fields = ['id', 'input_data', 'expected_output', 'is_hidden']



class QuestionSerializer(serializers.ModelSerializer):
    options = MCQOptionSerializer(many=True, required=False)
    images = QuestionImageSerializer(many=True, required=False)
    test_cases = CodeTestCaseSerializer(many=True, required=False)
    topic_names = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)

    class Meta:
        model = Question
        fields = [
            'id', 'serial_no', 'text', 'question_type', 'marks', 
            'negative_marks', 'individual_time_limit', 'correct_numerical',
            'options', 'images', 'test_cases', 'topic_names', 'topics'
        ]
        read_only_fields = ['topics']

    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        test_cases_data = validated_data.pop('test_cases', [])
        images_data = validated_data.pop('images', [])
        topic_names = validated_data.pop('topic_names', [])
        
        question = Question.objects.create(**validated_data)

        for name in topic_names:
            topic, _ = Topic.objects.get_or_create(name=name.strip().title())
            question.topics.add(topic)
        
        for option in options_data:
            MCQOption.objects.create(question=question, **option)
        for tc in test_cases_data:
            CodeTestCase.objects.create(question=question, **tc)
        for img in images_data:
            QuestionImage.objects.create(question=question, **img)
            
        return question

    
    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', None)
        test_cases_data = validated_data.pop('test_cases', None)
        images_data = validated_data.pop('images', None)
        topic_names = validated_data.pop('topic_names', None)

        # Update the main Question fields (text, marks, etc.)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update Topics
        if topic_names is not None:
            instance.topics.clear()
            for name in topic_names:
                topic, _ = Topic.objects.get_or_create(name=name.strip().title())
                instance.topics.add(topic)

        # Update Options (Delete old ones and recreate)
        if options_data is not None:
            instance.options.all().delete()
            for option in options_data:
                MCQOption.objects.create(question=instance, **option)

        # Update Test Cases
        if test_cases_data is not None:
            instance.test_cases.all().delete()
            for tc in test_cases_data:
                CodeTestCase.objects.create(question=instance, **tc)

        # Update Images
        if images_data is not None:
            instance.images.all().delete()
            for img in images_data:
                QuestionImage.objects.create(question=instance, **img)

        return instance

class TestSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source='questions.count', read_only=True)
    questions = QuestionSerializer(many=True, read_only=True)
    class Meta:
        model = Test
        fields = '__all__'

    def validate_start_time(self, value):
        if value and timezone.is_naive(value):
            # Get the IST timezone object
            ist = pytz.timezone('Asia/Kolkata')
            # Attach IST info to the time received from the slider
            return timezone.make_aware(value, ist)
        return value

    def validate_deadline(self, value):
        if value and timezone.is_naive(value):
            ist = pytz.timezone('Asia/Kolkata')
            return timezone.make_aware(value, ist)
        return value