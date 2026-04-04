# Online Examination Platform

## Use Cases

### Authentication & Role-Based Access

- Users can register using email OTP verification or Google OIDC login
- Separate portals for Teachers and Students
- Role assignment (Teacher/Student) based on portal used

### Classroom Management

- Teachers can create groups (e.g., Class 12 Physics, JEE 2026)
- Unique group code/link for student joining
- Join requests require teacher approval
- Teachers can remove students from groups

### Test Creation

- Teachers can create tests with:
  - Total timer (entire test duration)
  - Rapid-fire timer (per-question time limits)
- Flexible test availability:
  - Scheduled tests (fixed start time for all students)
  - Deadline-based tests (attempt anytime before deadline)
- Question shuffling per student

### Test Composition

- Supports multiple question types:
  - MCQ (with multiple correct answers)
  - Numerical (integer/float answers)
  - Coding (with visible and hidden test cases)
- Image support for questions
- Custom marking scheme:
  - Positive marks
  - Negative marking
  - Partial marking for MCQs

### Test Attempt (Student)

- Real-time test interface similar to competitive exams
- Countdown timer (total or per-question)
- Auto-submit on tab switch (basic proctoring)
- Coding questions executed in secure sandbox
- Immediate result generation after submission

### Evaluation & Scoring

- NTA-style scoring:
  - Correct answer → full marks
  - Wrong answer → negative marking
  - Unattempted → zero
  - Partial marking for MCQs (with penalty on incorrect selection)

### Analytics & History

- Test history for students and teachers
- Teachers can view all student results
- Students can view only their own performance
- Topic-wise performance analysis based on tagged questions

---

## Tech Stack

### Backend

- Django (Python)
- PostgreSQL

### Caching & Realtime Logic

- Redis (OTP storage, timer handling)

### Authentication

- Email OTP verification
- Google OIDC (OAuth 2.0)

### Media Storage

- ImageKit (for question images)

### Code Execution

- Dockerized sandbox environment
- Isolated containers for secure code execution

### Architecture (Apps)

- users → Authentication & RBAC
- classroom → Group management & membership
- testing → Test creation & configuration
- evaluation → Test attempts & scoring
- analytics → Performance tracking & insights
- docker → Code execution sandbox

### DevOps

- Docker
- Docker Compose

---

🚧 Project is actively under development.
