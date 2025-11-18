from django.contrib import admin
from django.urls import path, include
from api.views import unsubscribe
from api.admin_views import UserFilterView

urlpatterns = [
    path('admin/user-filter/', UserFilterView.as_view(), name='admin_user_filter'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/unsubscribe/<uuid:token>/', unsubscribe, name='unsubscribe'),
    path('twitter-auth/', include('twitter_auth.urls')),
]   
