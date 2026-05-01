from django.urls import path
from .views import RouteAPIView

urlpatterns = [
    path('route/', RouteAPIView.as_view(), name='route_api'),
]
