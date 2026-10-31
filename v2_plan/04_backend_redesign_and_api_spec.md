# 04. Backend Redesign & API Specification

> **Focus:** Detailed target architecture for the Django REST Framework backend, including the Service Layer pattern, custom declarative permissions, secure serializers, Celery background tasks, and standardized REST API contracts.

---

## 1. Target Directory & Modular Monolith Structure

To achieve clean separation of concerns and maintainability, the backend retains Django's modular app structure while introducing standard domain layers: **Services**, **Permissions**, and **Selectors**.

```
backend/
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yaml
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── celery.py               # Celery app initialization
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py             # Shared settings, apps, auth
│   │   ├── local.py            # Local dev settings (CORS, debug)
│   │   └── production.py       # Production settings (SSL, secure cookies)
│   └── urls.py                 # Root URLconf (REST API only, zero template views)
├── core/                       # Shared domain utilities across all apps
│   ├── __init__.py
│   ├── exceptions.py           # Custom exception handler & API error formats
│   ├── pagination.py           # Standard cursor/page-number pagination
│   └── permissions.py          # Global RBAC permissions (IsTeacher, IsStudent)
└── apps/
    ├── users/
    │   ├── models.py           # Custom User with email as USERNAME_FIELD
    │   ├── serializers.py      # Auth, profile, registration serializers
    │   ├── services.py         # AuthService (OTP, JWT, Google OAuth exchange)
    │   ├── permissions.py
    │   ├── views.py            # Thin HTTP controllers
    │   ├── urls.py
    │   └── tasks.py            # Celery email dispatch tasks
    ├── classroom/
    │   ├── models.py           # Group, Membership
    │   ├── serializers.py      # GroupSerializer, MembershipSerializer
    │   ├── services.py         # GroupService (join requests, member moderation)
    │   ├── permissions.py      # IsGroupTeacher, IsGroupMember
    │   ├── views.py
    │   └── urls.py
    ├── testing/
    │   ├── models.py           # Test, Question, Topic, MCQOption, CodeTestCase
    │   ├── serializers/
    │   │   ├── teacher.py      # TeacherTestSerializer (includes correct answers & testcases)
    │   │   └── student.py      # StudentTestSerializer (sanitized; answers stripped)
    │   ├── services.py         # TestManagementService (cloning, total marks sync)
    │   ├── permissions.py      # IsTestOwner
    │   ├── views.py
    │   └── urls.py
    ├── evaluation/
    │   ├── models.py           # TestAttempt, QuestionResponse
    │   ├── serializers.py      # AttemptSerializer, ResponseSubmissionSerializer
    │   ├── services/
    │   │   ├── scoring.py      # TestScoringService (NTA partial, negative marks)
    │   │   ├── timer.py        # RedisTimerService (TTL and session expiry)
    │   │   └── evaluation.py   # EvaluationService (coordinating code & answer validation)
    │   ├── permissions.py      # HasActiveAttempt
    │   ├── views.py
    │   ├── urls.py
    │   └── tasks.py            # Celery code execution worker tasks
    └── analytics/
        ├── serializers.py
        ├── services.py         # AnalyticsService (performance aggregation, topic breakdown)
        ├── views.py
        └── urls.py
```

---

## 2. Eliminating the Information Disclosure Bug: Dual Serializers

In V1, `TestSerializer` leaked answers to students. In V2, we strictly segregate Teacher and Student views and serializers.

### 2.1 Student Serializer (Sanitized)
```python
# apps/testing/serializers/student.py
from rest_framework import serializers
from apps.testing.models import Test, Question, MCQOption, QuestionImage

class StudentOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQOption
        fields = ['id', 'text']  # STRICTLY NO is_correct

class StudentQuestionSerializer(serializers.ModelSerializer):
    options = StudentOptionSerializer(many=True, read_only=True)
    images = serializers.SlugRelatedField(many=True, read_only=True, slug_field='image_url')

    class Meta:
        model = Question
        fields = [
            'id', 'serial_no', 'text', 'question_type', 
            'marks', 'individual_time_limit', 'options', 'images'
        ]  # STRICTLY NO correct_numerical, NO test_cases with expected_output

class StudentTestDetailSerializer(serializers.ModelSerializer):
    questions = StudentQuestionSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(source='questions.count', read_only=True)

    class Meta:
        model = Test
        fields = [
            'id', 'title', 'description', 'timer_type', 
            'total_duration', 'start_time', 'deadline', 
            'question_count', 'questions'
        ]
```

### 2.2 Dynamic Serializer Selection in ViewSets
```python
# apps/testing/views.py
class TestViewSet(viewsets.ModelViewSet):
    def get_serializer_class(self):
        if self.request.user.role == 'TEACHER':
            return TeacherTestSerializer
        return StudentTestDetailSerializer
```

---

## 3. Clean Architecture: Service Layer Implementation

Business logic is extracted from views into stateless service classes.

### 3.1 Evaluation Service Example
```python
# apps/evaluation/services/scoring.py
from decimal import Decimal
import json

class ScoringService:
    @staticmethod
    def evaluate_mcq(question, submitted_answer):
        """
        NTA Scoring:
        - Full marks if all correct options selected and no wrong options.
        - Negative marks if ANY wrong option is selected.
        - Partial marks if a subset of correct options is selected without any wrong option.
        """
        correct_ids = set(question.options.filter(is_correct=True).values_list('id', flat=True))
        if not correct_ids:
            return Decimal('0.0'), False

        try:
            if isinstance(submitted_answer, list):
                selected_ids = set(map(int, submitted_answer))
            else:
                parsed = json.loads(submitted_answer)
                selected_ids = set(map(int, parsed)) if isinstance(parsed, list) else {int(parsed)}
        except (ValueError, TypeError):
            return Decimal('0.0'), False

        if not selected_ids:
            return Decimal('0.0'), False

        wrong_selected = selected_ids - correct_ids
        correct_selected = selected_ids & correct_ids

        # If any incorrect option was chosen, apply full negative penalty
        if len(wrong_selected) > 0:
            return -abs(Decimal(str(question.negative_marks))), False

        # All correct options chosen
        if len(correct_selected) == len(correct_ids):
            return Decimal(str(question.marks)), True

        # Partial credit: proportional to correct choices
        partial_score = (Decimal(str(question.marks)) / Decimal(len(correct_ids))) * Decimal(len(correct_selected))
        return partial_score.quantize(Decimal('0.01')), False

    @staticmethod
    def evaluate_numerical(question, submitted_answer, tolerance=1e-3):
        try:
            val = float(submitted_answer)
            correct_val = float(question.correct_numerical)
            if abs(val - correct_val) <= tolerance:
                return Decimal(str(question.marks)), True
            return -abs(Decimal(str(question.negative_marks))), False
        except (ValueError, TypeError):
            return -abs(Decimal(str(question.negative_marks))), False
```

---

## 4. Declarative RBAC: Custom DRF Permissions

Replace ad-hoc inline `if` statements with declarative permission classes.

```python
# core/permissions.py
from rest_framework import permissions

class IsTeacher(permissions.BasePermission):
    """Allows access only to authenticated users with role TEACHER."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'TEACHER')

class IsStudent(permissions.BasePermission):
    """Allows access only to authenticated users with role STUDENT."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'STUDENT')

class IsGroupOwner(permissions.BasePermission):
    """Object-level permission to only allow group teachers to edit/delete."""
    def has_object_permission(self, request, view, obj):
        group = getattr(obj, 'group', obj)
        return group.teacher == request.user
```

---

## 5. Standardized API Response & Exception Handler

All endpoints follow a uniform JSON envelope to simplify frontend error handling and typing.

### 5.1 Response Structure
```json
// Success Response
{
  "success": true,
  "data": { ... },
  "message": "Operation successful"
}

// Error Response
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid credentials provided.",
    "details": {
      "email": ["Enter a valid email address."]
    }
  }
}
```

### 5.2 Custom DRF Exception Handler
```python
# core/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_code = getattr(exc, 'default_code', 'API_ERROR').upper()
        custom_data = {
            "success": False,
            "error": {
                "code": error_code,
                "message": str(exc.detail) if hasattr(exc, 'detail') and isinstance(exc.detail, str) else "A request error occurred.",
                "details": response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
            }
        }
        response.data = custom_data

    return response
```

---

## 6. Celery Asynchronous Worker Architecture

```python
# apps/evaluation/tasks.py
from celery import shared_task
from apps.evaluation.models import TestAttempt, Question
from apps.evaluation.services.sandbox import SandboxRunner

@shared_task(time_limit=30, soft_time_limit=25)
def execute_code_test_cases_task(attempt_id, question_id, source_code):
    """
    Executes code inside an isolated sandbox container, saving results asynchronously.
    """
    question = Question.objects.get(id=question_id)
    test_cases = question.test_cases.all()
    
    results = []
    for tc in test_cases:
        output = SandboxRunner.run(
            language=question.programming_language,
            code=source_code,
            stdin=tc.input_data,
            timeout_seconds=2
        )
        passed = (output['stdout'].strip() == tc.expected_output.strip())
        results.append({
            "test_case_id": tc.id,
            "is_hidden": tc.is_hidden,
            "passed": passed,
            "stdout": output['stdout'] if not tc.is_hidden else None,
            "error": output['stderr'] or output['error']
        })
    
    return results
```

---

## 7. Complete V2 REST API Contract Specification

### 7.1 Authentication (`/api/v1/auth/`)
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register/` | Public | Register with email, password, role, name (triggers async OTP). |
| `POST` | `/api/v1/auth/verify-otp/` | Public | Verify OTP and activate account for specified role. |
| `POST` | `/api/v1/auth/login/` | Public | Authenticate with email, password, role (returns JWT pair). |
| `POST` | `/api/v1/auth/token/refresh/` | Public | Refresh expired access token using refresh token. |
| `POST` | `/api/v1/auth/password-reset/` | Public | Send password reset OTP. |
| `POST` | `/api/v1/auth/reset-password/` | Public | Reset password with OTP. |
| `GET` | `/api/v1/auth/google/` | Public | Initiates Google OIDC flow. |
| `GET` | `/api/v1/auth/google/callback/`| Public | Exchanging code, redirects to frontend `http://localhost:3000/auth/callback?token=...`. |
| `GET` | `/api/v1/auth/me/` | Authenticated | Retrieve current user profile. |
| `GET` | `/api/v1/auth/imagekit-auth/` | Teacher | Get ImageKit upload signature for question images. |

### 7.2 Classroom & Groups (`/api/v1/classroom/`)
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/classroom/groups/` | Authenticated | List groups (Teacher: owned; Student: approved memberships). |
| `POST` | `/api/v1/classroom/groups/` | Teacher | Create a new classroom group. |
| `GET` | `/api/v1/classroom/groups/{id}/` | Group Member | View group details. |
| `PUT/PATCH`| `/api/v1/classroom/groups/{id}/` | Group Teacher | Update group name/description. |
| `DELETE`| `/api/v1/classroom/groups/{id}/` | Group Teacher | Delete group and all tests. |
| `POST` | `/api/v1/classroom/groups/join/` | Student | Request to join a group using `invite_code`. |
| `GET` | `/api/v1/classroom/groups/{id}/members/` | Group Member | List members and pending requests. |
| `POST` | `/api/v1/classroom/groups/{id}/moderate/` | Group Teacher | Approve, reject, or remove a student. |

### 7.3 Tests & Question Composition (`/api/v1/testing/`)
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/testing/tests/?group={id}` | Authenticated | List published tests for group. |
| `POST` | `/api/v1/testing/tests/` | Teacher | Create a new test draft. |
| `GET` | `/api/v1/testing/tests/{id}/` | Authenticated | Get test detail (Teacher: full; Student: questions without answers). |
| `PATCH`| `/api/v1/testing/tests/{id}/` | Test Owner | Update settings (duration, deadline, publish). |
| `DELETE`| `/api/v1/testing/tests/{id}/` | Test Owner | Delete draft test. |
| `POST` | `/api/v1/testing/tests/{id}/publish/` | Test Owner | Publish test to students. |
| `POST` | `/api/v1/testing/tests/{id}/questions/` | Test Owner | Add question (MCQ, Numerical, Code). |
| `PATCH`| `/api/v1/testing/questions/{id}/` | Test Owner | Update question details (draft tests only). |
| `DELETE`| `/api/v1/testing/questions/{id}/` | Test Owner | Remove question from test. |

### 7.4 Live Exam & Evaluation (`/api/v1/evaluation/`)
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/evaluation/tests/{test_id}/start/` | Student | Start exam attempt (creates attempt, initializes Redis timer, returns sanitized questions). |
| `POST` | `/api/v1/evaluation/attempts/{id}/run-code/` | Attempt Student | Run code against visible test cases (asynchronous task, returns job ID). |
| `GET` | `/api/v1/evaluation/jobs/{job_id}/` | Attempt Student | Check execution job result. |
| `POST` | `/api/v1/evaluation/attempts/{id}/submit-answer/` | Attempt Student | Submit answer for a question (saves answer, validates timer). |
| `POST` | `/api/v1/evaluation/attempts/{id}/log-violation/` | Attempt Student | Record tab-switch event; auto-disqualifies after 3 violations. |
| `POST` | `/api/v1/evaluation/attempts/{id}/finish/` | Attempt Student | Finalize exam attempt, compute final NTA score, delete Redis timer. |

### 7.5 Results & Analytics (`/api/v1/analytics/`)
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/group/{id}/results/` | Group Member | Group test overview with scores (released tests only). |
| `GET` | `/api/v1/analytics/test/{id}/summary/` | Teacher | Full score sheet of all students with warning counts and completion times. |
| `GET` | `/api/v1/analytics/test/{id}/paper/?student_id={id}` | Auth (Owner/Teacher) | Full test paper review (question by question, marks earned, submitted vs correct answers). |
| `GET` | `/api/v1/analytics/student/me/` | Student | Historical performance metrics and topic-wise breakdown. |

