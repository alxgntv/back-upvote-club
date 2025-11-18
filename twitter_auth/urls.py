from django.urls import path
from .views import AuthDashboardView, TwitterAuthView, TwitterServiceCallbackView

urlpatterns = [
    path('auth-dashboard/', AuthDashboardView.as_view(), name='auth_dashboard'),
    path('authorize/<int:account_id>/', TwitterAuthView.as_view(), name='twitter_auth'),
    path('service-callback/', TwitterServiceCallbackView.as_view(), name='twitter_service_callback'),
]