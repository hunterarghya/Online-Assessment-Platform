# 01. Codebase Audit & Architectural Review

> **Scope:** Full-stack assessment of the existing Django codebase, data models, business logic, endpoints, security, and current template layer.

---

## 1. Executive Assessment & Maturity Scorecard

The current codebase is a **functional prototype (V1)**. It was clearly written to establish feature proof-of-concept rapidly ("make it work"). While the domain modeling correctly captures the core business entities of an examination system, the implementation violates several foundational backend principles and presents critical vulnerabilities that prevent it from being production-ready.

| Criterion | Current Grade | Production Expectation | Core Gap |
| :--- | :---: | :---: | :--- |
| **Security & Isolation** | **F** | **A+** | Remote Code Execution (RCE) as root; test answers exposed in API. |
| **Architecture & Separation** | **D** | **A** | Fat views; zero service layer; backend returns raw inline HTML/JS. |
| **Concurrency & Non-blocking** | **D-** | **A** | Synchronous code execution (up to 50s blocking Gunicorn); synchronous SMTP. |
| **Data Integrity & Modeling** | **C-** | **A** | Username collisions; N+1 query loops; missing DB indexes. |
| **API Contract & Design** | **C** | **A** | Inconsistent JSON shapes; no OpenAPI schema; missing custom permissions. |
| **Testing & Verification** | **F (0%)** | **A** | Every `tests.py` file is empty. Zero automated tests. |
| **Frontend Maintainability** | **F** | **A** | 3,000+ lines of raw HTML templates with inline vanilla JS and DOM mutations. |

---

## 2. Evaluation Against Backend First Principles

### Principle 1: Least Privilege & Zero-Trust Security (CRITICAL FAIL)
Backend systems that accept and evaluate untrusted user code or manage sensitive examination data must adhere to strict zero-trust boundaries.

#### 1.1 Remote Code Execution (RCE) as Root
- **Location:** `apps/evaluation/utils.py` (lines 3–26) and `Dockerfile` (lines 34–49).
- **The Issue:**
  ```python
  def evaluate_code_glot(language_key, source_code, stdin_data):
      process = subprocess.Popen(
          ['python3', '-c', source_code],
          stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          text=True
      )
  ```
  The code execution runs directly on the web container without containerization, namespaces, or cgroups.
- **Impact:** The Dockerfile executes as `root`. Any student submitting code via `run_code` or `submit_answer` can execute arbitrary Python commands:
  - Read environment secrets (`os.environ` containing `SECRET_KEY`, `DATABASE_URL`, `IMAGEKIT_PRIVATE_KEY`).
  - Read or wipe the database directly from Python.
  - Access the Docker host network.

#### 1.2 Information Disclosure: Test Answers Leaked to Students
- **Location:** `apps/testing/views.py` (lines 8–21) and `apps/testing/serializers.py` (lines 28–41, 103–109).
- **The Issue:**
  `TestViewSet` permits students to query `/api/testing/tests/<test_id>/`. The view uses `TestSerializer`, which serializes `QuestionSerializer`:
  ```python
  class MCQOptionSerializer(serializers.ModelSerializer):
      class Meta:
          model = MCQOption
          fields = ['id', 'text', 'is_correct']  # <-- is_correct is exposed!

  class CodeTestCaseSerializer(serializers.ModelSerializer):
      class Meta:
          model = CodeTestCase
          fields = ['id', 'input_data', 'expected_output', 'is_hidden']  # <-- expected_output exposed!
  ```
- **Impact:** Any student opening the browser DevTools or issuing a `curl` request to the test endpoint receives all MCQ correct options, numerical answers, and hidden test cases before the exam begins.

#### 1.3 Weak Pseudorandom Number Generation for Security Tokens
- **Location:** `apps/users/services.py` (line 17):
  ```python
  def generate_otp(email):
      otp = str(random.randint(100000, 999999))
  ```
- **The Issue:** `random.randint` uses the Mersenne Twister PRNG, which is completely deterministic and insecure for cryptographic use.
- **Production Standard:** Must use Python's `secrets` module (`secrets.randbelow` or `secrets.SystemRandom`).

---

### Principle 2: Non-Blocking I/O & Concurrency Scalability (FAIL)
A web API worker (Gunicorn/Uvicorn) should never perform long-running CPU-bound or blocking I/O work inside an HTTP request-response cycle.

#### 2.1 Synchronous Code Execution Blocking Workers
- **Location:** `apps/evaluation/views.py` (`run_code` and `submit_answer`).
- **The Issue:** When a student clicks "Run Code", the request synchronously calls `evaluate_code_glot` for every test case. With a 5-second timeout and 10 test cases, a single request can block a Gunicorn worker process for up to 50 seconds.
- **Impact:** In an exam of 50 students, just 4 students submitting code simultaneously will exhaust all standard Gunicorn workers (typically 4 workers on Render/AWS), causing complete request timeouts (HTTP 502/504) for all other students trying to submit answers or load questions.

#### 2.2 Synchronous SMTP Email Delivery
- **Location:** `apps/users/views.py` (`RegisterView.post` and `RequestPasswordResetView.post`).
- **The Issue:** `send_otp_email` invokes `django.core.mail.send_mail` synchronously connecting to `smtp.gmail.com:587`.
- **Impact:** Third-party SMTP handshakes take 1,500ms to 5,000ms. If Gmail rate-limits or Render network latency spikes, user registration hangs. If SMTP fails, the user record is created in an unverified state while returning an HTTP 500.

---

### Principle 3: Separation of Concerns & Clean Architecture (FAIL)
In production systems, views handle HTTP requests/responses and delegation; serializers handle input validation and data serialization; services encapsulate business workflows; models encapsulate data structure and database operations.

#### 3.1 Backend Emitting Frontend HTML/JavaScript
- **Location:** `apps/users/views.py` (lines 200–207):
  ```python
  content = f"""
  <script>
      localStorage.setItem('token', '{access_token}');
      localStorage.setItem('user', JSON.stringify({json.dumps(user_data)}));
      window.location.href = '/dashboard/';
  </script>
  """
  return HttpResponse(content)
  ```
- **The Issue:** An API endpoint directly renders HTML and browser JavaScript to manipulate `localStorage` and perform client-side redirects. This completely breaks when the frontend is decoupled (e.g. running on `localhost:3000` or a separate domain like `app.testron.com`).

#### 3.2 Monolithic Fat Views with Inlined Domain Logic
- In `apps/evaluation/views.py`, `submit_answer` spans 140+ lines doing:
  - Global Redis timer validation
  - Per-question lockout logic
  - Inlined MCQ partial grading algorithms
  - Floating-point numerical comparison
  - Synchronous code execution
  - Database updates wrapped in manual `transaction.atomic()`
- Domain logic is scattered and duplicated between `run_code` and `submit_answer`.

---

### Principle 4: Data Modeling Integrity & Query Efficiency (POOR)

#### 4.1 Fatal Username Collision Flaw
- **Location:** `apps/users/models.py` (lines 22–27) & `serializers.py` (lines 17–26):
  ```python
  def save(self, *args, **kwargs):
      suffix = f"_{self.role.lower()}"
      if not self.username.endswith(suffix):
          self.username = f"{self.email.split('@')[0]}{suffix}"
      super().save(*args, **kwargs)
  ```
- **The Bug:** If `alex.smith@gmail.com` and `alex.smith@university.edu` both register as students, both generate the username `alex.smith_student`. Because `username` is unique on `AbstractUser`, the second registration crashes with an unhandled DB integrity exception (`UniqueConstraintViolation`).
- **Remediation:** Remove reliance on `username` entirely or set `username = str(uuid.uuid4())` and configure `USERNAME_FIELD = 'email'`.

#### 4.2 Cross-Role Verification Bleed
- **Location:** `apps/users/views.py` (line 63):
  ```python
  if verify_otp(email, otp):
      User.objects.filter(email=email).update(is_verified=True)
  ```
- **The Bug:** If an email is registered as both a TEACHER and a STUDENT, verifying the OTP for one account inadvertently marks **both** accounts as verified, bypassing role-specific validation.

#### 4.3 Severe N+1 Query Loops
- **Location:** `apps/classroom/serializers.py`:
  ```python
  def get_member_count(self, obj):
      return obj.memberships.filter(status=Membership.Status.APPROVED).count()
  ```
  Fetching a list of 50 groups executes 51 SQL queries instead of 1 query with `annotate(member_count=Count(...))`.
- **Location:** `apps/analytics/views.py` (`GroupResultsView` and `TestStudentSummaryView`):
  Iterates over lists of models in Python loops, executing multiple database lookups per item.

#### 4.4 Missing Model Attributes & Buggy Timezone Handling
- In `apps/evaluation/views.py`:
  ```python
  lang_key = getattr(question, 'programming_language', 'python').lower()
  ```
  The `Question` model does not have a `programming_language` field defined! It defaults to Python silently.
- In `apps/testing/serializers.py`:
  ```python
  def validate_start_time(self, value):
      if value and timezone.is_naive(value):
          ist = pytz.timezone('Asia/Kolkata') # NameError: name 'pytz' is not defined!
  ```
  `pytz` is never imported in the serializer. If a naive datetime is passed, it triggers a 500 runtime crash.

---

### Principle 5: Role-Based Access Control (RBAC) & Authorization (INCOMPLETE)
- DRF provides a robust, declarative permission framework (`BasePermission`).
- Currently, permissions are checked ad-hoc inside view methods:
  ```python
  if request.user.role != 'TEACHER':
      return Response({"error": "Only teachers can upload images"}, status=403)
  ```
- In `GroupViewSet.perform_create`, there is **no check** verifying if `request.user.role == 'TEACHER'`. Any student can issue a `POST /api/classroom/groups/` and become the teacher of their own group.
- `CORS_ALLOW_ALL_ORIGINS = True` is hardcoded in `settings.py`, allowing any external website to send authenticated cross-origin requests if credentials are leaked.

---

## 3. Review of the Current Frontend (Template Layer)

Although the user assumed the frontend was standard Server-Side Rendering (SSR), inspection shows it is actually **5 monolithic HTML files** containing **thousands of lines of inline vanilla JavaScript and CSS**:

```
templates/
├── index.html          (294 lines: Auth, tabs, commented-out forms, Google login)
├── dashboard.html      (799 lines: Modals, student/teacher logic, raw DOM injection)
├── exam_hall.html      (983 lines: Timer intervals, NTA palette, Monaco-like tabs)
├── test_composer.html  (669 lines: Dynamic form generators, ImageKit script tags)
└── results.html        (380 lines: Paper rendering, raw score tables)
```

### Critical Frontend Anti-Patterns Observed:
1. **Direct DOM Mutation via `innerHTML`**:
   Components are dynamically rendered by concatenating HTML strings:
   ```javascript
   container.innerHTML += `<div class="card">${escapeHtml(data.name)}</div>`;
   ```
   This is error-prone, violates clean component reuse, and introduces Cross-Site Scripting (XSS) risks.
2. **State Management via Global Variables**:
   In `exam_hall.html` and `dashboard.html`, state is managed via loose `let` variables in the global browser scope (`let currentQuestion = 0;`, `let timerInterval;`, `let responses = {};`). When an async fetch fails, UI and state desynchronize without error recovery.
3. **Commented-Out Dead Code**:
   `index.html` has lines 82–159 commented out with raw HTML comments, leaving only Google login active and masking broken password reset flows.
4. **Hardcoded URLs and Mixed Concerns**:
   API paths (`/api/auth/`, `/api/classroom/`) and navigation redirects (`window.location.href = '/dashboard/'`) are hardcoded directly into inline event handlers.

---

## 4. Audit Summary & Grade Conclusion

The V1 codebase succeeded in its initial mission: proving that an online assessment platform with multiple question types, tab-switch proctoring, and automated evaluation can work.

However, to transition from a **fragile prototype** to a **production-grade enterprise platform**, the backend must be refactored to enforce strict security boundaries, non-blocking asynchronous execution, and clean architectural layers, while the frontend must be cleanly separated into a modern, component-driven SPA.

