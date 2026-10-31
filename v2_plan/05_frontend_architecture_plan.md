# 05. Frontend Architecture Plan

> **Objective:** Design a modern, component-driven, decoupled Single Page Application (SPA) to replace the 5 monolithic Django HTML templates. Emphasizes UI simplicity, reusable components, exam hall timer resilience, and maintainability.

---

## 1. Technology Stack Specification

```
┌────────────────────────────────────────────────────────┐
│                      FRONTEND V2                       │
│  React 18/19 + TypeScript + Vite + Tailwind CSS        │
├────────────────────────────────────────────────────────┤
│ UI Primitives:    shadcn/ui (Radix UI)                 │
│ Icons:            Lucide React                         │
│ Server State:     TanStack Query v5 (React Query)      │
│ Routing:          React Router v6 / v7                 │
│ Forms:            React Hook Form + Zod                │
│ Code Editor:      @monaco-editor/react (VS Code Engine)│
│ Math Rendering:   KaTeX (react-katex)                  │
│ Data Viz:         Recharts (Topic Analytics)           │
│ HTTP Client:      Axios with JWT auto-refresh          │
└────────────────────────────────────────────────────────┘
```

---

## 2. Target Directory Structure (Feature-Driven Architecture)

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── src/
│   ├── main.tsx                # App entry point & provider wrapper
│   ├── App.tsx                 # Route tree definitions
│   ├── api/                    # Centralized Axios instance & interceptors
│   │   ├── client.ts           # Base API client with JWT refresh logic
│   │   └── endpoints.ts        # Typed endpoint constants
│   ├── assets/                 # SVGs, brand assets, logos
│   ├── components/             # Reusable UI component library
│   │   ├── ui/                 # shadcn/ui primitives (Button, Dialog, Tabs, etc.)
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── input.tsx
│   │   │   ├── textarea.tsx
│   │   │   └── toast.tsx
│   │   ├── common/             # Cross-cutting layout components
│   │   │   ├── Navbar.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── RoleGuard.tsx   # Protects teacher vs student routes
│   │   │   ├── ErrorBoundary.tsx
│   │   │   └── FullscreenPrompt.tsx
│   │   └── math/
│   │       └── MathRenderer.tsx # High-performance KaTeX formula renderer
│   ├── features/               # Domain-specific feature modules
│   │   ├── auth/
│   │   │   ├── components/     # LoginForm, RegisterForm, OTPModal, GoogleButton
│   │   │   ├── hooks/          # useAuth, useGoogleLogin
│   │   │   ├── pages/          # LoginPage, RegisterPage, OAuthCallbackPage
│   │   │   └── authStore.ts    # User session state (Zustand or Context)
│   │   ├── classroom/
│   │   │   ├── components/     # GroupCard, MemberListModal, JoinGroupModal
│   │   │   ├── hooks/          # useGroups, useGroupMembers
│   │   │   └── pages/          # TeacherDashboard, StudentDashboard
│   │   ├── composer/           # Test creation feature
│   │   │   ├── components/     # QuestionEditor, MCQOptionsBuilder, TestCaseList
│   │   │   ├── hooks/          # useTestComposer, useImageKitUpload
│   │   │   └── pages/          # TestComposerPage, TestSettingsPage
│   │   ├── exam/               # Live exam hall
│   │   │   ├── components/     # QuestionArea, NtaPalette, ExamHeader, CodingConsole
│   │   │   ├── hooks/          # useExamTimer, useProctoring, useSubmitAnswer
│   │   │   └── pages/          # ExamWaitingRoom, ExamHallPage
│   │   └── analytics/          # Scorecards & reporting
│   │       ├── components/     # Scorecard, TopicChart, QuestionReviewCard
│   │       └── pages/          # StudentResultsPage, TeacherTestSummaryPage
│   ├── hooks/                  # Global utility hooks
│   │   ├── useTimer.ts         # Resilient countdown timer with server sync
│   │   ├── useFullscreen.ts    # Fullscreen lock & listener
│   │   └── useDebounce.ts
│   └── types/                  # Global TypeScript contracts
│       ├── api.ts              # API response envelopes
│       ├── auth.ts             # User, Role, Token interfaces
│       ├── classroom.ts        # Group, Membership
│       ├── test.ts             # Test, Question, MCQOption, TestCase
│       └── exam.ts             # Attempt, Response, NTAStatus
```

---

## 3. Core Architectural Modules

### 3.1 Authentication & Centralized Axios Client
In V1, JWT tokens were read from and written to `localStorage` in each inline script. In V2, Axios manages headers and automatic token refresh via interceptors.

```typescript
// src/api/client.ts
import axios from 'axios';
import { useAuthStore } from '@/features/auth/authStore';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

// Request Interceptor: Attach Bearer Token
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response Interceptor: Seamless Refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const newAccessToken = await useAuthStore.getState().refreshTokens();
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().logout();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);
```

---

### 3.2 Exam Hall Architecture: Timer & Proctoring Resilience

The Exam Hall is the most critical user-facing screen. It must guarantee **fairness, zero state loss, and strict anti-cheating enforcement**.

#### A. Resilient Server-Synchronized Timer Hook (`useExamTimer`)
Local client timers (`Date.now()`) are vulnerable to user tampering (adjusting system clock) and can drift when browser tabs background.
```typescript
// src/features/exam/hooks/useExamTimer.ts
import { useState, useEffect, useRef } from 'react';

interface TimerProps {
  endTimestampUnix: number;  // End timestamp provided by server (seconds)
  serverTimeUnix: number;    // Server time at start
  onExpire: () => void;
}

export function useExamTimer({ endTimestampUnix, serverTimeUnix, onExpire }: TimerProps) {
  // Compute server-client time offset
  const clientStart = Math.floor(Date.now() / 1000);
  const offsetRef = useRef<number>(serverTimeUnix - clientStart);

  const calculateRemaining = () => {
    const currentAdjustedTime = Math.floor(Date.now() / 1000) + offsetRef.current;
    return Math.max(0, endTimestampUnix - currentAdjustedTime);
  };

  const [secondsRemaining, setSecondsRemaining] = useState<number>(calculateRemaining);

  useEffect(() => {
    if (secondsRemaining <= 0) {
      onExpire();
      return;
    }

    const interval = setInterval(() => {
      const remaining = calculateRemaining();
      setSecondsRemaining(remaining);
      if (remaining <= 0) {
        clearInterval(interval);
        onExpire();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [endTimestampUnix]);

  const minutes = Math.floor(secondsRemaining / 60);
  const seconds = secondsRemaining % 60;
  const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  return { secondsRemaining, formattedTime, isUrgent: secondsRemaining < 300 };
}
```

#### B. Anti-Cheating & Proctoring Hook (`useProctoring`)
Listens to browser visibility and tab switching, sending audit pings to `/log-violation/`.
```typescript
// src/features/exam/hooks/useProctoring.ts
import { useEffect, useRef } from 'react';
import { apiClient } from '@/api/client';

export function useProctoring(attemptId: string, onDisqualify: () => void, onWarn: (count: number) => void) {
  const isTerminated = useRef(false);

  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.hidden && !isTerminated.current) {
        try {
          const res = await apiClient.post(`/evaluation/attempts/${attemptId}/log-violation/`);
          if (res.data.action === 'DISQUALIFY') {
            isTerminated.current = true;
            onDisqualify();
          } else if (res.data.action === 'WARN') {
            onWarn(res.data.warnings_current);
          }
        } catch (err) {
          console.error("Failed to log violation", err);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [attemptId]);
}
```

---

### 3.3 Exam Hall Screen Layout Design

```
┌────────────────────────────────────────────────────────────────────────┐
│ TESTRON | Physics Final Exam         Timer: [ 42:15 ]  [ Submit Test ] │
├─────────────────────────────────────────────┬──────────────────────────┤
│ Question 4 of 25            Marks: +4 / -1  │ Question Palette         │
│                                             │ ┌───┬───┬───┬───┬───┐    │
│ Topic: Kinematics                           │ │ 1 │ 2 │ 3 │ 4*│ 5 │    │
│ A particle of mass m moves under the force  │ ├───┼───┼───┼───┼───┤    │
│ F = -k*x. Find the period of oscillation:   │ │ 6 │ 7 │ 8 │ 9 │ 10│    │
│                                             │ └───┴───┴───┴───┴───┘    │
│   (A) T = 2 * pi * sqrt(m / k)              │                          │
│   (B) T = pi * sqrt(k / m)                  │ Status Legend:           │
│   (C) T = 2 * pi * sqrt(k / m)              │ 🟢 Answered              │
│   (D) T = sqrt(m / k)                       │ 🔴 Not Answered          │
│                                             │ 🟣 Marked for Review     │
│ [ Clear Response ]      [ Mark for Review ] │ ⚪ Not Visited           │
│                                             │                          │
│ [ ← Previous ]                 [ Next → ]   │ Tab Violations: 1 / 3 ⚠️ │
└─────────────────────────────────────────────┴──────────────────────────┘
```

---

### 3.4 Coding Question Interface: Monaco Editor & Console

For coding questions, the exam hall seamlessly toggles into an integrated development environment:
- **Left Panel (50%):** Problem statement, input/output constraints, sample test cases, and KaTeX math formulas.
- **Right Panel (50%):**
  - Language selector dropdown (Python 3, Java, C++, JavaScript).
  - **Monaco Editor** with syntax highlighting, autocomplete, and theme options (Dark / Light).
  - Bottom Tabbed Console:
    - **Custom Test Input (stdin)**
    - **Run Code Results:** Visual cards indicating `Passed` (green) or `Failed` (red) with actual vs expected output for visible test cases.
    - **Terminal Error Log:** Displays `stderr` or syntax errors directly.

---

## 4. Reusable UI Components Directory

Building clean, reusable components is essential to replace the copy-pasted HTML snippets in the V1 templates.

| Component | Responsibility | Usage |
| :--- | :--- | :--- |
| `Button.tsx` | Standardized button with variants (`primary`, `secondary`, `destructive`, `ghost`) and loading spinner state. | Replaces 20+ inconsistent `<button>` tags across templates. |
| `Modal.tsx` / `Dialog.tsx` | Accessible modal dialog with backdrop blur, keyboard ESC dismissal, and focus trap. | Replaces manual `document.getElementById('modal').style.display = 'block'`. |
| `StatusBadge.tsx` | Pill badge with color coding for statuses (`APPROVED`, `PENDING`, `DISQUALIFIED`, `COMPLETED`). | Used across Classroom rosters and Results tables. |
| `QuestionPaletteItem.tsx` | Square button representing an exam question with NTA color states (answered, review, unvisited). | Replaces inline `.q-circle` HTML rendering. |
| `ImageUploader.tsx` | Drag-and-drop file uploader integrating directly with ImageKit client-side auth. | Used in Test Composer to attach diagrams to questions. |
| `DataTable.tsx` | Sortable, paginated table component built with TanStack Table. | Used in Teacher Summary and Student Gradebook. |

---

## 5. Migration Strategy: Zero-Downtime Transition

```
┌────────────────────────────────────────────────────────┐
│ STEP 1: Deploy Standalone Frontend (Vite + React)      │
│ Hosted on separate port (5173 local, or CDN in prod)   │
├────────────────────────────────────────────────────────┤
│ STEP 2: Configure Reverse Proxy (Nginx)                │
│ • Path /api/*       ──► Forward to Django (Port 8000)  │
│ • Path /*           ──► Serve React SPA static bundle  │
├────────────────────────────────────────────────────────┤
│ STEP 3: Deprecate Django Template Views                │
│ Remove TemplateView routes in `config/urls.py`         │
│ Delete `templates/*.html` directory                    │
└────────────────────────────────────────────────────────┘
```

By decoupling the frontend into a standalone static build, the backend becomes a pure, stateless JSON API. Both teams or features can iterate independently without breaking template tags or deployment dependencies.

