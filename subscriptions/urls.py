from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    # Plans
    path('plans/', views.list_plans, name='list-plans'),

    # User subscription
    path('current/', views.current_subscription, name='current-subscription'),
    path('usage/', views.usage_stats, name='usage-stats'),
    path('history/', views.transaction_history, name='transaction-history'),

    # Actions
    path('check-limit/', views.check_limit, name='check-limit'),
    path('use-credits/', views.use_credits, name='use-credits'),
    path('upgrade/', views.upgrade_plan, name='upgrade-plan'),
]
