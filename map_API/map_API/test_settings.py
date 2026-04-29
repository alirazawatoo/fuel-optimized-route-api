import os
os.environ['DJANGO_DEBUG'] = 'true'
from .settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
ALLOWED_HOSTS = ['testserver', 'localhost']
ORS_API_KEY = 'synthetic-test-key'
ORS_URL = 'https://ors.invalid/v2/directions/driving-car'
REST_FRAMEWORK = {'DEFAULT_THROTTLE_RATES': {'route': '1000/minute'}}
