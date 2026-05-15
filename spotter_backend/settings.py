import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get(
    "SPOTTER_SECRET_KEY",
    "django-insecure-spotter-backend-development",
)
DEBUG = env_bool("SPOTTER_DEBUG", default=True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("SPOTTER_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "fuel",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "spotter_backend.middleware.OpenPanelAPIMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "spotter_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "spotter_backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "fuel_plan": os.environ.get("SPOTTER_FUEL_PLAN_THROTTLE", "60/min"),
    },
}

OSRM_BASE_URL = "https://router.project-osrm.org"
OSRM_ROUTE_OVERVIEW = "full"
CENSUS_GEOCODER_BASE_URL = "https://geocoding.geo.census.gov/geocoder"
CENSUS_BATCH_GEOCODER_TIMEOUT = 60
ROUTE_CANDIDATE_PROJECTION_SPACING_MILES = 5
DEFAULT_ROUTE_CORRIDOR_MILES = 10
MAX_ROUTE_CORRIDOR_MILES = 25
DEFAULT_MAX_RANGE_MILES = 500
DEFAULT_MILES_PER_GALLON = 10

OPENPANEL_CLIENT_ID = os.environ.get(
    "OPENPANEL_CLIENT_ID",
    "fdd09eb0-04b6-4dd4-a42c-d06d3d8e98de",
)
OPENPANEL_CLIENT_SECRET = os.environ.get("OPENPANEL_CLIENT_SECRET", "")
OPENPANEL_API_URL = os.environ.get(
    "OPENPANEL_API_URL",
    "https://openpanel.jainparichay.in/api",
).rstrip("/")
OPENPANEL_DISABLED = env_bool("OPENPANEL_DISABLED", default=False)
