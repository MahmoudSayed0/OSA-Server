from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('refresh/', views.refresh_token_view, name='refresh'),
    path('google/', views.google_auth_view, name='google_auth'),
    path('me/', views.me_view, name='me'),
    path('profile/', views.update_profile_view, name='update_profile'),
]
