from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads tokens from httpOnly cookies.
    Falls back to Authorization header if cookie is not present.
    """

    def authenticate(self, request):
        # Try to get token from cookie first
        access_token = request.COOKIES.get('access_token')

        if access_token:
            try:
                validated_token = self.get_validated_token(access_token)
                user = self.get_user(validated_token)
                return (user, validated_token)
            except AuthenticationFailed:
                # Token is invalid or expired, try header
                pass
            except Exception:
                # Other errors, try header
                pass

        # Fall back to header-based auth (Authorization: Bearer <token>)
        return super().authenticate(request)
