import json
import os
import tempfile
import unittest
from contextlib import closing
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

test_storage = tempfile.TemporaryDirectory()
os.environ["AUTH_DB_PATH"] = os.path.join(test_storage.name, "auth.sqlite3")
os.environ["TEACHER_ACCOUNTS"] = "[]"

from src import app as api


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        os.environ["TEACHER_ACCOUNTS"] = json.dumps(
            [
                {
                    "email": "teacher@mergington.edu",
                    "name": "Teacher",
                    "password": "teacher-password-123",
                }
            ]
        )
        with closing(api.connect_auth_db()) as connection:
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM users")
            connection.commit()
        api.initialize_auth_store()

    def test_student_registration_and_login(self):
        registration = api.StudentRegistration(
            email="Student@mergington.edu",
            name="Student Name",
            password="student-password-123",
            grade=11,
        )
        registered = api.register_student(registration)

        self.assertEqual(registered["email"], "student@mergington.edu")
        self.assertEqual(registered["role"], "student")
        self.assertNotIn("password", registered)

        login = api.login(
            api.LoginRequest(
                email="student@mergington.edu",
                password="student-password-123",
            )
        )
        self.assertEqual(login["user"]["role"], "student")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=login["access_token"]
        )
        self.assertEqual(api.get_current_user(credentials)["email"], registered["email"])

    def test_registration_rejects_non_school_email(self):
        registration = api.StudentRegistration(
            email="student@example.com",
            name="Student Name",
            password="student-password-123",
        )
        with self.assertRaises(HTTPException) as raised:
            api.register_student(registration)
        self.assertEqual(raised.exception.status_code, 400)

    def test_duplicate_registration_is_rejected(self):
        registration = api.StudentRegistration(
            email="student@mergington.edu",
            name="Student Name",
            password="student-password-123",
        )
        api.register_student(registration)
        with self.assertRaises(HTTPException) as raised:
            api.register_student(registration)
        self.assertEqual(raised.exception.status_code, 409)

    def test_teacher_credentials_are_server_configured(self):
        login = api.login(
            api.LoginRequest(
                email="teacher@mergington.edu",
                password="teacher-password-123",
            )
        )
        self.assertEqual(login["user"]["role"], "teacher")

    def test_role_dependencies_reject_wrong_role(self):
        student = {
            "email": "student@mergington.edu",
            "name": "Student",
            "grade": 11,
            "role": "student",
        }
        teacher = {
            "email": "teacher@mergington.edu",
            "name": "Teacher",
            "grade": None,
            "role": "teacher",
        }
        with self.assertRaises(HTTPException) as student_error:
            api.require_teacher(student)
        with self.assertRaises(HTTPException) as teacher_error:
            api.require_student(teacher)
        self.assertEqual(student_error.exception.status_code, 403)
        self.assertEqual(teacher_error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
