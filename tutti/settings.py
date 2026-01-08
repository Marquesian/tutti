import os
import os.path
from email.utils import getaddresses

import environ

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def getenv_with_file(key: str, default: str = None) -> str:
    """Returns the value of the environment variable or from a file.

    If the environment variable is not set, this function will check if an
    environment variable with _FILE appended exists and return the contents of
    that file.
    """
    value = os.getenv(key)
    if value:
        return value
    filename = os.getenv("{}_FILE".format(key))
    if filename:
        with open(filename) as f:
            return f.read()
    return default


# Import .env file
env = environ.Env()
env_file = str(os.path.join(BASE_DIR, ".env"))
if os.path.exists(env_file):
    environ.Env.read_env(env_file=env_file)

SECRET_KEY = getenv_with_file('DJANGO_SECRET_KEY')

DEBUG = env.bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1').split(',')

# Application definition

INSTALLED_APPS = [
    # Own apps
    'members.apps.MembersConfig',  # members should be above the admin site so that it can override admin templates
    'sync.apps.SyncConfig',
    'oidc.apps.OIDCConfig',
    'pages.apps.PagesConfig',
    'pennotools.apps.PennotoolsConfig',
    'duqduqgo.apps.DuqduqgoConfig',
    'donors.apps.DonorsConfig',
    'faqts.apps.FaQtsConfig',
    # Admin site
    'tutti.apps.TuttiAdminConfig',

    # Django apps
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Library apps
    'phonenumber_field',
    'localflavor',
    'django_countries',
    'health_check',  # django-health-check
    'health_check.db',
    'health_check.storage',
    'import_export',  # django-import-export
    'django_q',
    'bootstrap4',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # We're using WhiteNoise for the static files
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tutti.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pages.context_processors.source_commit',
            ],
        },
    },
]

WSGI_APPLICATION = 'tutti.wsgi.application'

DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=0)
# Allow overriding database password using separate environment variable
database_password = getenv_with_file("DATABASE_PASSWORD")
if database_password:
    DATABASES["default"]["PASSWORD"] = database_password

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Europe/Amsterdam'
USE_I18N = False
# USE_L10N = False
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'frontend/dist'),
]
# We're using WhiteNoise in production
STATIC_ROOT = os.getenv('DJANGO_STATIC_ROOT', None)
if os.getenv('DJANGO_WHITENOISE', None):
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.getenv('DJANGO_MEDIA_ROOT', None)

AUTH_USER_MODEL = 'members.User'

# LDAP settings
LDAP_HOST = os.getenv('DJANGO_LDAP_HOST')  # Can be in URI form
LDAP_USER = os.getenv('DJANGO_LDAP_USER')
LDAP_PASSWORD = getenv_with_file('DJANGO_LDAP_PASSWORD')
LDAP_START_TLS = env.bool("DJANGO_LDAP_START_TLS", default=False)
# When True, an LDAP sync will be triggered after saving a person or group.
LDAP_SYNC_ON_SAVE = env.bool("DJANGO_LDAP_SYNC_ON_SAVE", default=False)

PHONENUMBER_DEFAULT_REGION = 'NL'

# OpenID Connect configuration
#
# If not set, OIDC will not be used.
AUTHLIB_OAUTH_CLIENTS = {
    'keycloak': {
        'client_id': os.getenv('OIDC_CLIENT_ID'),
        'client_secret': getenv_with_file('OIDC_CLIENT_SECRET'),
        'server_metadata_url': os.getenv('OIDC_METADATA_URL')
    }
}
# See OIDC spec, needs to have place a placeholder '{}' where the redirect URI will be placed
OIDC_END_SESSION_ENDPOINT = os.getenv('OIDC_END_SESSION_ENDPOINT')

# When users need to be logged in, the OpenID Connect flow will be started by
# the login view.
LOGIN_URL = 'oidc:login'

# Set up logging for some of our modules
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'msg': {
            'format': '{asctime} {name} {levelname:8s} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'debug': {
            # Logs debug messages to console when DEBUG=True
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'msg',
        },
    },
    'loggers': {
        'pennotools': {
            'handlers': ['debug'],
            'level': 'DEBUG',
        },
    },
}

# E-mail settings
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
SERVER_EMAIL = os.getenv('DJANGO_SERVER_EMAIL', 'root@localhost')
DEFAULT_FROM_EMAIL = os.getenv('DJANGO_DEFAULT_FROM_EMAIL', 'webmaster@localhost')
# E-mail address string where 5xx errors are sent, e.g. 'Me <my@address.net>, Someone Else <his@address.com>'
ADMINS = getaddresses([os.getenv('DJANGO_ADMINS', default='')])
MEMBERSHIP_REQUEST_RECIPIENT = os.getenv('DJANGO_MEMBERSHIP_REQUEST_RECIPIENT', 'subscriptions@esmgquadrivium.nl')

# Ensure cookies over HTTPS
if env.bool('DJANGO_COOKIE_SECURE', default=False):
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

# We assume to be running behind a reverse proxy (only effective in production environment)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Setup task queue
Q_CLUSTER = {
    'workers': 1,  # We need 1 worker because we don't want parallel task runs
    'timeout': 600,  # Tasks are terminated after 10 minutes
    'ack_failures': True,  # Do not retry failed tasks
    'retry': 3600,  # (Retries are disabled so this doesn't do anything)
    'catch_up': False,
    'orm': 'default',
    'poll': 30,  # Poll the database every 30 seconds for tasks
}

# ID of the group in the database that holds the current Quadrivium members.
MEMBERS_GROUP = env.int("MEMBERS_GROUP", default=-1)

# Bootstrap layout settings
BOOTSTRAP4 = {
    # "set_placeholder": False,
    'horizontal_label_class': 'col-sm-2',
    'horizontal_field_class': 'col-sm-10',
}

# Authentication settings for Microsoft Graph API
GRAPH_TENANT = os.getenv("GRAPH_TENANT")
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID")
GRAPH_CLIENT_SECRET = getenv_with_file("GRAPH_CLIENT_SECRET")
# Sync with Azure when a user or group is saved
GRAPH_SYNC_ON_SAVE = env.bool("GRAPH_SYNC_ON_SAVE", default=False)
# This license will be assigned when a new user is created in Azure
GRAPH_LICENSE_SKU_ID = os.getenv("GRAPH_LICENSE_SKU_ID")

# Set Matplotlib config+cache directory
os.environ['MPLCONFIGDIR'] = '/tmp/matplotlib'

# https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
