# Mergington High School Activities API

A super simple FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Sign up for activities
- Register and authenticate student accounts with school email addresses
- Authenticate teacher accounts provisioned through server-side configuration

## Getting Started

1. Install the dependencies:

   ```
   pip install fastapi uvicorn
   ```

2. Run the application:

   ```
   python app.py
   ```

3. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| GET    | `/activities`                                                     | Get all activities with their details and current participant count |
| POST   | `/activities/{activity_name}/signup?email=student@mergington.edu` | Sign up for an activity                                             |
| POST   | `/auth/register`                                                  | Register a student account                                          |
| POST   | `/auth/login`                                                     | Authenticate and receive a bearer token                             |
| GET    | `/auth/me`                                                        | Get the authenticated user's profile                                |

Student registration requires an `@mergington.edu` email address, name, and
password of at least 12 characters. Grade is optional. Teacher accounts cannot
be registered publicly; provision them in the server environment using the
`TEACHER_ACCOUNTS` JSON setting. Store this setting in your deployment's secret
manager, not in source control. For example:

```json
[
  {
    "email": "teacher@mergington.edu",
    "name": "School Teacher",
    "password": "<a unique password of at least 12 characters>"
  }
]
```

The API stores salted password hashes and persists accounts and sessions in
SQLite. The database defaults to `src/auth.sqlite3`; set `AUTH_DB_PATH` to
choose another persistent location. Login returns an access token; send it on
authenticated requests in the `Authorization` header using the bearer scheme.
Sessions expire after 12 hours. `require_student` and `require_teacher` are
backend dependency helpers for task endpoints, so task-related APIs can enforce
roles server-side.

## Data Model

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

Activity data is stored in memory and resets when the server restarts. Student
accounts and authentication sessions are stored in SQLite and persist across
restarts.
