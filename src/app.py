"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

auth_db_path = Path(os.environ.get("AUTH_DB_PATH", current_dir / "auth.sqlite3"))
auth_db_path.parent.mkdir(parents=True, exist_ok=True)
bearer_scheme = HTTPBearer(auto_error=False)
school_email_pattern = re.compile(r"^[^@\s]+@mergington\.edu$", re.IGNORECASE)
session_lifetime_seconds = 12 * 60 * 60


class StudentRegistration(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    grade: int | None = Field(default=None, ge=9, le=12)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
    )
    return f"{salt.hex()}:{password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, expected_hash_hex = stored_hash.split(":", maxsplit=1)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(expected_hash_hex)
    except ValueError:
        return False

    actual_hash = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1
    )
    return hmac.compare_digest(actual_hash, expected_hash)


dummy_password_hash = hash_password(secrets.token_urlsafe(24))


def connect_auth_db() -> sqlite3.Connection:
    connection = sqlite3.connect(auth_db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_auth_store() -> None:
    teacher_accounts_json = os.environ.get("TEACHER_ACCOUNTS", "[]")
    try:
        teacher_accounts = json.loads(teacher_accounts_json)
    except json.JSONDecodeError as error:
        raise RuntimeError("TEACHER_ACCOUNTS must be a JSON array") from error

    if not isinstance(teacher_accounts, list):
        raise RuntimeError("TEACHER_ACCOUNTS must be a JSON array")

    with closing(connect_auth_db()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                grade INTEGER,
                role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
                password_hash TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )
        """)
        for account in teacher_accounts:
            if not isinstance(account, dict):
                raise RuntimeError("Each TEACHER_ACCOUNTS entry must be an object")
            email = account.get("email")
            name = account.get("name")
            password = account.get("password")
            if (
                not isinstance(email, str)
                or not school_email_pattern.fullmatch(email.strip())
                or not isinstance(name, str)
                or not name.strip()
                or not isinstance(password, str)
                or len(password) < 12
            ):
                raise RuntimeError(
                    "Each teacher account needs a school email, name, "
                    "and password of at least 12 characters"
                )
            connection.execute(
                """
                INSERT INTO users (email, name, role, password_hash)
                VALUES (?, ?, 'teacher', ?)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    role = 'teacher',
                    password_hash = excluded.password_hash
                """,
                (normalize_email(email), name.strip(), hash_password(password)),
            )
        connection.commit()


def public_user(user: sqlite3.Row) -> dict[str, str | int | None]:
    return {
        "email": user["email"],
        "name": user["name"],
        "grade": user["grade"],
        "role": user["role"],
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str | int | None]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    now = int(time.time())
    with closing(connect_auth_db()) as connection:
        user = connection.execute(
            """
            SELECT users.email, users.name, users.grade, users.role
            FROM sessions
            JOIN users ON users.email = sessions.email
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return public_user(user)


def require_student(
    user: dict[str, str | int | None] = Depends(get_current_user),
) -> dict[str, str | int | None]:
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return user


def require_teacher(
    user: dict[str, str | int | None] = Depends(get_current_user),
) -> dict[str, str | int | None]:
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return user


initialize_auth_store()


# In-memory activity database
activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}


@app.post("/auth/register", status_code=201)
def register_student(account: StudentRegistration):
    email = normalize_email(account.email)
    name = account.name.strip()
    if not school_email_pattern.fullmatch(email):
        raise HTTPException(
            status_code=400,
            detail="Use a valid @mergington.edu school email address",
        )
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    try:
        with closing(connect_auth_db()) as connection:
            connection.execute(
                """
                INSERT INTO users (email, name, grade, role, password_hash)
                VALUES (?, ?, ?, 'student', ?)
                """,
                (
                    email,
                    name,
                    account.grade,
                    hash_password(account.password),
                ),
            )
            connection.commit()
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="An account already exists for this email"
        ) from error

    return {
        "email": email,
        "name": name,
        "grade": account.grade,
        "role": "student",
    }


@app.post("/auth/login")
def login(account: LoginRequest):
    email = normalize_email(account.email)
    with closing(connect_auth_db()) as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

    password_hash = user["password_hash"] if user is not None else dummy_password_hash
    if not verify_password(account.password, password_hash) or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = int(time.time()) + session_lifetime_seconds
    with closing(connect_auth_db()) as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, email, expires_at) VALUES (?, ?, ?)",
            (token_hash, email, expires_at),
        )
        connection.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": session_lifetime_seconds,
        "user": public_user(user),
    }


@app.get("/auth/me")
def read_current_user(
    user: dict[str, str | int | None] = Depends(get_current_user),
):
    return user


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up"
        )

    # Add student
    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity"
        )

    # Remove student
    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}
