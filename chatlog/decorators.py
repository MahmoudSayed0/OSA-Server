"""
Admin-only decorators for the Safety Agent backend.
"""

from functools import wraps
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


def require_staff(view_func):
    """
    Decorator to ensure the user is authenticated via JWT and is staff/superuser.

    Usage:
        @require_staff
        def admin_dashboard(request):
            # Only staff/superuser can access this view
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Manually authenticate JWT token
        jwt_auth = JWTAuthentication()

        try:
            # Authenticate the request
            auth_result = jwt_auth.authenticate(request)

            if auth_result is None:
                return JsonResponse({
                    'error': 'Authentication required',
                    'detail': 'No valid authentication credentials provided.'
                }, status=401)

            user, token = auth_result
            request.user = user

        except AuthenticationFailed as e:
            return JsonResponse({
                'error': 'Authentication failed',
                'detail': str(e)
            }, status=401)
        except Exception as e:
            return JsonResponse({
                'error': 'Authentication error',
                'detail': str(e)
            }, status=401)

        # Check if user is staff or superuser
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({
                'error': 'Admin access required',
                'detail': 'You must be a staff member or superuser to access this endpoint.'
            }, status=403)

        # User is authorized, proceed with the view
        return view_func(request, *args, **kwargs)

    return wrapper
