import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env', override=False)

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-sofizadmin-key-2026-prod')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '*').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # Local Apps
    'monitoring.apps.MonitoringConfig',
    'projects.apps.ProjectsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database Setup: Use Postgres if available, fallback to SQLite
DB_NAME = os.getenv('POSTGRES_DB')
DB_USER = os.getenv('POSTGRES_USER')
DB_PASS = os.getenv('POSTGRES_PASSWORD')
DB_HOST = os.getenv('POSTGRES_HOST')
DB_PORT = os.getenv('POSTGRES_PORT', '5432')

if DB_NAME and DB_USER and DB_HOST:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASS,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
            'CONN_MAX_AGE': 0,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Algiers'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5172',
    'http://127.0.0.1:5172',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5174',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://epay.sofizpay.com:8383',
    'http://epay.sofizpay.com',
    'https://epay.sofizpay.com',
    'http://91.98.137.59:8383',
    'http://91.98.137.59',
]

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5172')

# Email Configuration - Enabled for Operational Quota Refill Alerts & System Notifications
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_ALERTS_ENABLED = True
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'eurlsofizpay@gmail.com')
_raw_email_pass = os.getenv('EMAIL_PASSWORD', os.getenv('EMAIL_HOST_PASSWORD', 'gdjjabmkujkfwjzy'))
EMAIL_HOST_PASSWORD = _raw_email_pass.replace(' ', '') if _raw_email_pass else 'gdjjabmkujkfwjzy'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'eurlsofizpay@gmail.com')
DEFAULT_ERROR_ALERT_EMAIL = os.getenv('DEFAULT_ERROR_ALERT_EMAIL', 'rabeh2020ken@gmail.com')
ADMIN_ALERT_EMAILS = [e.strip() for e in os.getenv('ADMIN_ALERT_EMAILS', 'rabeh2020ken@gmail.com,admin@sofizpay.com').split(',') if e.strip()]
track_NOTIFICATION_EMAIL = os.getenv('track_NOTIFICATION_EMAIL', 'gaming@sofizpay.com')
ADMIN_NOTIFICATION_EMAIL = os.getenv('ADMIN_NOTIFICATION_EMAIL', 'rabeh2020ken@gmail.com')

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'monitoring.authentication.CombinedAPIKeyOrJWTAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/minute',
        'user': '1000/minute',
        'login': '15/minute',
    },
}

# SimpleJWT Institutional Security Configuration
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer', 'JWT'),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}
# OpenWA WhatsApp Configuration
OPENWA_BASE_URL = os.getenv('OPENWA_BASE_URL', 'https://whats.sofizpay.com')
OPENWA_API_KEY = os.getenv('OPENWA_API_KEY', 'owa_k1_b76726a2ba218f3af77e6a84f82eb4c00fc7e1290ad714bd9d0739b10d7961cc')
OPENWA_SESSION_ID = os.getenv('OPENWA_SESSION_ID', '5169c587-641a-46c3-a6a2-4bd4329439ae')

# Obfuscated / Secret Django Admin Portal URL Path
# Prevents bot scans, brute force, and discovery of the administrative console
ADMIN_URL_PATH = os.getenv('DJANGO_ADMIN_URL', '8f2a9c37/').strip('/') + '/'
LOGIN_URL = '/' + ADMIN_URL_PATH + 'login/'
LOGIN_REDIRECT_URL = '/' + ADMIN_URL_PATH

# Obfuscated Secret API Prefix to prevent scanning and unauthorized endpoint discovery
API_SECRET_PREFIX = os.getenv('API_SECRET_PREFIX', 'sec_8f2a9c37').strip('/')
API_URL_PREFIX = f"{API_SECRET_PREFIX}/" if API_SECRET_PREFIX else ""


