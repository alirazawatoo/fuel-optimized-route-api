import os
os.environ['DJANGO_DEBUG'] = 'true'
from .settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
ALLOWED_HOSTS = ['testserver', 'localhost']
ORS_API_KEY = 'synthetic-test-key'
