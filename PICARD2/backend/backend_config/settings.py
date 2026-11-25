import os
from pathlib import Path
from dotenv import load_dotenv

DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-this-is-just-for-local-testing-change-in-prod',
)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'db'), # Matches the service name in docker-compose
        'PORT': os.environ.get('DB_PORT', '3306'),
    }
}
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
# Acknowledge a task only after it finishes and reserve one task at a time, so
# a worker that dies before finishing a task lets the broker deliver it again.
# The worker's Queued -> Running claim makes a repeated delivery harmless.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Upper limit on the runs one parameter sweep may create.
SWEEP_MAX_EXPERIMENTS = int(os.environ.get('SWEEP_MAX_EXPERIMENTS', '100'))

def _split_csv_env(name, default=''):
    raw_value = os.environ.get(name, default)
    return [item.strip() for item in raw_value.split(',') if item.strip()]


ALLOWED_HOSTS = _split_csv_env('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0')

# Media files (User-uploaded datasets, scripts, etc.)
MEDIA_URL = '/media/'
STATIC_URL = '/static/'
ROOT_URLCONF = 'backend_config.urls'
WSGI_APPLICATION = 'backend_config.wsgi.application'


# Point the MEDIA_ROOT to the shared Docker volume.
# We use a fallback to a local 'media' folder so it doesn't crash if run outside Docker.
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
INSTALLED_APPS = [
    # 1. Default Django apps (Core functionality)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',  # <-- This specifically fixes your current error!
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 2. Third-party apps
    'corsheaders',
    'rest_framework',               # <-- Required for your serializers and JsonResponse

    # 3. Your local apps
    'experiments',                  # <-- Tells Django where to find your models and views
    'authentication',
    'datasets',
    'scripts'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', # Manages user sessions
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware', # Manages user logins
    'django.contrib.messages.middleware.MessageMiddleware', # Manages popup alerts
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

frontend_local_url = os.environ.get('FRONTEND_LOCAL_URL', 'http://localhost:3000').rstrip('/')
frontend_remote_url = os.environ.get('FRONTEND_REMOTE_URL', '').rstrip('/')

CORS_ALLOWED_ORIGINS = [url for url in [frontend_local_url, frontend_remote_url] if url]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS.copy()

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

GITHUB_OAUTH_APPS = {
    'local': {
        'client_id': os.environ.get('GITHUB_OAUTH_LOCAL_CLIENT_ID', ''),
        'client_secret': os.environ.get('GITHUB_OAUTH_LOCAL_CLIENT_SECRET', ''),
        'frontend_url': frontend_local_url,
    },
    'remote': {
        'client_id': os.environ.get('GITHUB_OAUTH_REMOTE_CLIENT_ID', ''),
        'client_secret': os.environ.get('GITHUB_OAUTH_REMOTE_CLIENT_SECRET', ''),
        'frontend_url': frontend_remote_url,
    },
}

GITHUB_OAUTH_SCOPE = 'read:user user:email read:org'
GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_API_URL = 'https://api.github.com/user'
GITHUB_EMAILS_API_URL = 'https://api.github.com/user/emails'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], # You can add custom template directories here later if needed
        'APP_DIRS': True, # Tells Django to look inside INSTALLED_APPS for templates
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

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
