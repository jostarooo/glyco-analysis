from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from system.auth import AuthError, AuthService, hash_password, verify_password


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class PasswordTests(unittest.TestCase):
    def test_hash_round_trip_and_wrong_password(self) -> None:
        encoded = hash_password("correct horse")
        self.assertTrue(verify_password("correct horse", encoded))
        self.assertFalse(verify_password("wrong", encoded))
        self.assertNotIn("correct horse", encoded)

    def test_malformed_hash_is_rejected(self) -> None:
        self.assertFalse(verify_password("anything", "not-a-valid-hash"))


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.auth = AuthService.with_password(
            "demo",
            "secret",
            session_ttl=timedelta(minutes=5),
            max_failures=2,
            lockout=timedelta(minutes=1),
            clock=self.clock,
        )

    def test_authenticate_create_and_expire_session(self) -> None:
        self.auth.authenticate("demo", "secret", "127.0.0.1")
        session = self.auth.create_session("demo")
        self.assertEqual(self.auth.get_session(session.token), session)
        self.clock.advance(minutes=6)
        self.assertIsNone(self.auth.get_session(session.token))

    def test_repeated_failures_lock_the_identity(self) -> None:
        with self.assertRaises(AuthError) as first:
            self.auth.authenticate("demo", "wrong", "127.0.0.1")
        self.assertEqual(first.exception.code, "INVALID_CREDENTIALS")
        with self.assertRaises(AuthError) as context:
            self.auth.authenticate("demo", "wrong", "127.0.0.1")
        self.assertEqual(context.exception.code, "LOGIN_LOCKED")
        with self.assertRaises(AuthError) as context:
            self.auth.authenticate("demo", "secret", "127.0.0.1")
        self.assertEqual(context.exception.status, 429)

    def test_logout_invalidates_the_session(self) -> None:
        self.auth.authenticate("demo", "secret", "127.0.0.1")
        session = self.auth.create_session("demo")
        self.auth.destroy_session(session.token)
        self.assertIsNone(self.auth.get_session(session.token))


if __name__ == "__main__":
    unittest.main()
