"""
Development settings for Storm Cloud Server.

Use this for local development with manage.py runserver.
"""

import os
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

# Development-friendly ALLOWED_HOSTS
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,*', cast=Csv())

# Database - SQLite by default (inherited from base.py)
# No override needed - just use the SQLite config from base.py

# Console email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Simple console logging for development
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Disable CSRF for easier API testing (dev only!)
# CSRF_COOKIE_SECURE = False
# SESSION_COOKIE_SECURE = False

# Show detailed error pages
DEBUG_PROPAGATE_EXCEPTIONS = False

# Django Debug Toolbar (if installed)
if 'debug_toolbar' in INSTALLED_APPS:
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1', 'localhost']
