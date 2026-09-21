"""Settings used by the test suite.

Plain static storage (no collectstatic needed), fast password hashing and an
in-memory mail backend, so the suite runs in seconds.
"""

from .settings import *  # noqa: F401,F403

DEBUG = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Never call the real API from tests.
GEMINI_API_KEY = ""
AI_ENABLED = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
