from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestViewSet, TopicViewSet, QuestionViewSet

router = DefaultRouter()
router.register(r'tests', TestViewSet, basename='test')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'questions', QuestionViewSet, basename='question')

urlpatterns = [
    path('', include(router.urls)),
]