from django.urls import path
from .views import GroupResultsView, TestPaperView, TestStudentSummaryView

urlpatterns = [
    path('group/<int:group_id>/', GroupResultsView.as_view(), name='group-results'),
    path('test/<uuid:test_id>/summary/', TestStudentSummaryView.as_view(), name='test-student-summary'),
    path('test/<uuid:test_id>/paper/', TestPaperView.as_view(), name='test-paper-view'),
]