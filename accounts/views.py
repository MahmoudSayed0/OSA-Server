from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import timedelta

from .serializers import UserSerializer, RegisterSerializer, LoginSerializer, GoogleAuthSerializer

User = get_user_model()


def get_tokens_for_user(user):
    """Generate JWT tokens for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def set_auth_cookies(response, tokens):
    """Set httpOnly cookies for authentication tokens."""
    # Access token - shorter lifetime
    response.set_cookie(
        'access_token',
        tokens['access'],
        httponly=True,
        secure=not settings.DEBUG,  # True in production
        samesite='Lax',
        max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
        path='/',
    )
    # Refresh token - longer lifetime
    response.set_cookie(
        'refresh_token',
        tokens['refresh'],
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path='/',
    )
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Register a new user with email and password."""
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        tokens = get_tokens_for_user(user)

        response = Response({
            'user': UserSerializer(user).data,
            'message': 'Registration successful'
        }, status=status.HTTP_201_CREATED)

        return set_auth_cookies(response, tokens)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Login with email and password."""
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        # Try to authenticate
        user = authenticate(request, username=email, password=password)

        if user is not None:
            tokens = get_tokens_for_user(user)

            response = Response({
                'user': UserSerializer(user).data,
                'message': 'Login successful'
            })

            return set_auth_cookies(response, tokens)

        return Response(
            {'error': 'Invalid email or password'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_view(request):
    """Authenticate with Google OAuth token."""
    serializer = GoogleAuthSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data['token']

        try:
            # Verify the Google token
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )

            # Extract user info from token
            email = idinfo.get('email', '').lower()
            google_id = idinfo.get('sub')
            name = idinfo.get('name', '')
            picture = idinfo.get('picture', '')

            if not email:
                return Response(
                    {'error': 'Email not provided by Google'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Try to find existing user by email or google_id
            user = None
            created = False

            try:
                user = User.objects.get(email=email)
                # Link Google account if not already linked
                if not user.google_id:
                    user.google_id = google_id
                    user.avatar_url = picture
                    if not user.full_name and name:
                        user.full_name = name
                    user.save()
            except User.DoesNotExist:
                # Create new user
                username = email.split('@')[0]
                # Ensure username is unique
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                user = User.objects.create(
                    email=email,
                    username=username,
                    google_id=google_id,
                    full_name=name,
                    avatar_url=picture,
                )
                created = True

            tokens = get_tokens_for_user(user)

            response = Response({
                'user': UserSerializer(user).data,
                'message': 'Google authentication successful',
                'created': created
            })

            return set_auth_cookies(response, tokens)

        except ValueError as e:
            return Response(
                {'error': f'Invalid Google token: {str(e)}'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            return Response(
                {'error': f'Google authentication failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Logout user by clearing auth cookies."""
    response = Response({'message': 'Logout successful'})
    response.delete_cookie('access_token', path='/')
    response.delete_cookie('refresh_token', path='/')
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """Refresh the access token using the refresh token from cookie."""
    refresh_token = request.COOKIES.get('refresh_token')

    if not refresh_token:
        return Response(
            {'error': 'Refresh token not found'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        refresh = RefreshToken(refresh_token)
        access_token = str(refresh.access_token)

        response = Response({'message': 'Token refreshed successfully'})
        response.set_cookie(
            'access_token',
            access_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite='Lax',
            max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
            path='/',
        )
        return response

    except Exception as e:
        response = Response(
            {'error': 'Invalid or expired refresh token'},
            status=status.HTTP_401_UNAUTHORIZED
        )
        response.delete_cookie('access_token', path='/')
        response.delete_cookie('refresh_token', path='/')
        return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Get current authenticated user's information."""
    return Response(UserSerializer(request.user).data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_profile_view(request):
    """Update current user's profile."""
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
