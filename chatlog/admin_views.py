"""
Admin-only views for the Oinride Safety Agent Admin Panel.

These endpoints are protected by the @require_staff decorator and require
the user to be authenticated as a staff member or superuser.
"""

import json
from datetime import timedelta
from django.http import JsonResponse
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .decorators import require_staff
from .models import (
    UserKnowledgeBase,
    UploadedPDF,
    ChatSession,
    ChatMessage,
    FoundationDocument,
    DocumentSummary,
    UserFeedback,
    SavedNote,
)
from subscriptions.models import UserSubscription, SubscriptionPlan

User = get_user_model()


# ==============================
# AUTHENTICATION
# ==============================

@csrf_exempt
@require_http_methods(["POST"])
def admin_login(request):
    """
    Admin-only login endpoint.

    POST /chatlog/admin/login/
    Body: {"username": "admin", "password": "password"}

    Returns JWT tokens and admin user info if credentials are valid and user is staff.
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return JsonResponse({
                'error': 'Missing credentials',
                'detail': 'Both username and password are required.'
            }, status=400)

        # Authenticate user
        user = authenticate(username=username, password=password)

        if user is None:
            return JsonResponse({
                'error': 'Invalid credentials',
                'detail': 'Username or password is incorrect.'
            }, status=401)

        # Check if user is staff or superuser
        if not (user.is_staff or user.is_superuser):
            return JsonResponse({
                'error': 'Access denied',
                'detail': 'You must be a staff member to access the admin panel.'
            }, status=403)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return JsonResponse({
            'access': access_token,
            'refresh': refresh_token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON',
            'detail': 'Request body must be valid JSON.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Login failed',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def admin_me(request):
    """
    Get current admin user details.

    GET /chatlog/admin/me/
    """
    user = request.user
    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'date_joined': user.date_joined.isoformat(),
    })


# ==============================
# DASHBOARD ANALYTICS
# ==============================

@require_staff
@require_http_methods(["GET"])
def dashboard_stats(request):
    """
    Get overview statistics for the dashboard.

    GET /chatlog/admin/dashboard/stats/

    Returns total counts of users, documents, sessions, and credits used.
    Also includes friendly marketing statistics for Foundation KB power.
    """
    try:
        # Get total counts
        total_users = User.objects.filter(is_staff=False).count()
        total_documents = UploadedPDF.objects.count()
        total_sessions = ChatSession.objects.count()
        total_messages = ChatMessage.objects.count()

        # Get foundation documents count
        total_foundation_docs = FoundationDocument.objects.count()

        # Get counts from last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        active_users_30d = User.objects.filter(
            is_staff=False,
            date_joined__gte=thirty_days_ago
        ).count()
        new_documents_30d = UploadedPDF.objects.filter(
            uploaded_at__gte=thirty_days_ago
        ).count()
        new_sessions_30d = ChatSession.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()

        # Calculate storage used (sum of all PDF file sizes in MB)
        from django.db.models import Sum
        total_storage_bytes = UploadedPDF.objects.aggregate(
            total=Sum('file_size')
        )['total'] or 0
        storage_used_mb = total_storage_bytes / (1024 * 1024)  # Convert bytes to MB

        # ============================================
        # FRIENDLY KB STATISTICS (Marketing Data)
        # ============================================
        from django.db import connection

        # Get total chunks from vector database
        total_chunks = 0
        foundation_chunks = 0
        user_chunks = 0
        try:
            with connection.cursor() as cursor:
                # Total chunks in system
                cursor.execute("SELECT count(*) FROM langchain_pg_embedding")
                total_chunks = cursor.fetchone()[0]

                # Foundation KB chunks (from foundation_mining_kb collection)
                cursor.execute("""
                    SELECT count(*) FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name = 'foundation_mining_kb'
                """)
                foundation_chunks = cursor.fetchone()[0]

                # User document chunks
                user_chunks = total_chunks - foundation_chunks
        except Exception as e:
            print(f"[Dashboard] Could not fetch chunk stats: {e}")

        # Calculate total pages memorized (from uploaded PDFs)
        total_pages = UploadedPDF.objects.aggregate(
            total=Sum('page_count')
        )['total'] or 0

        # Foundation pages
        foundation_pages = FoundationDocument.objects.aggregate(
            total=Sum('page_count')
        )['total'] or 0

        # Estimate words analyzed (roughly 250 words per chunk on average)
        total_words_analyzed = total_chunks * 250
        foundation_words = foundation_chunks * 250

        # Format large numbers for display
        def format_number(num):
            if num >= 1000000:
                return f"{num/1000000:.1f}M"
            elif num >= 1000:
                return f"{num/1000:.1f}K"
            return str(num)

        return JsonResponse({
            # Basic stats
            'total_users': total_users,
            'total_documents': total_documents,
            'total_sessions': total_sessions,
            'total_messages': total_messages,
            'total_foundation_docs': total_foundation_docs,
            'active_users_30d': active_users_30d,
            'storage_used_mb': round(storage_used_mb, 2),

            # ============================================
            # FRIENDLY KB STATISTICS
            # ============================================
            'kb_stats': {
                # Total system stats
                'total_chunks': total_chunks,
                'total_chunks_display': format_number(total_chunks),
                'total_pages_memorized': total_pages + foundation_pages,
                'total_pages_display': format_number(total_pages + foundation_pages),
                'total_words_analyzed': total_words_analyzed,
                'total_words_display': format_number(total_words_analyzed),

                # Foundation KB power stats (marketing friendly)
                'foundation': {
                    'documents': total_foundation_docs,
                    'chunks': foundation_chunks,
                    'chunks_display': format_number(foundation_chunks),
                    'pages': foundation_pages,
                    'pages_display': format_number(foundation_pages),
                    'words': foundation_words,
                    'words_display': format_number(foundation_words),
                },

                # User documents stats
                'user_docs': {
                    'documents': total_documents,
                    'chunks': user_chunks,
                    'chunks_display': format_number(user_chunks),
                    'pages': total_pages,
                    'pages_display': format_number(total_pages),
                }
            }
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch dashboard stats',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def user_growth_data(request):
    """
    Get user growth data for the last 30 days.

    GET /chatlog/admin/dashboard/user-growth/

    Returns daily user registration counts.
    """
    try:
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get daily user counts
        user_growth = (
            User.objects
            .filter(is_staff=False, date_joined__gte=thirty_days_ago)
            .annotate(date=TruncDate('date_joined'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        # Convert to list of dicts with formatted dates
        growth_data = [
            {
                'date': item['date'].isoformat(),
                'count': item['count']
            }
            for item in user_growth
        ]

        return JsonResponse({'growth_data': growth_data})

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user growth data',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def document_upload_data(request):
    """
    Get document upload trends for the last 30 days.

    GET /chatlog/admin/dashboard/document-uploads/
    """
    try:
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get daily document upload counts
        upload_data = (
            UploadedPDF.objects
            .filter(uploaded_at__gte=thirty_days_ago)
            .annotate(date=TruncDate('uploaded_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        # Convert to list of dicts
        uploads = [
            {
                'date': item['date'].isoformat(),
                'count': item['count']
            }
            for item in upload_data
        ]

        return JsonResponse({'upload_data': uploads})

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch document upload data',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def recent_activity(request):
    """
    Get recent activity feed (last 50 activities).

    GET /chatlog/admin/dashboard/recent-activity/

    Returns a mixed feed of user registrations, document uploads, and chat sessions.
    """
    try:
        # Get recent user registrations
        recent_users = User.objects.filter(is_staff=False).order_by('-date_joined')[:15]
        user_activities = [
            {
                'type': 'user_registration',
                'user_id': user.id,
                'username': user.username,
                'timestamp': user.date_joined.isoformat(),
                'description': f'New user registered: {user.username}'
            }
            for user in recent_users
        ]

        # Get recent document uploads
        recent_docs = UploadedPDF.objects.select_related('user_knowledge_base').order_by('-uploaded_at')[:15]
        doc_activities = [
            {
                'type': 'document_upload',
                'document_id': doc.id,
                'filename': doc.filename,
                'username': doc.user_knowledge_base.username if doc.user_knowledge_base else 'Unknown',
                'timestamp': doc.uploaded_at.isoformat(),
                'description': f'{doc.user_knowledge_base.username if doc.user_knowledge_base else "Unknown"} uploaded {doc.filename}'
            }
            for doc in recent_docs
        ]

        # Get recent chat sessions
        recent_sessions = ChatSession.objects.select_related('user_knowledge_base').order_by('-created_at')[:15]
        session_activities = [
            {
                'type': 'chat_session',
                'session_id': session.session_id,
                'username': session.user_knowledge_base.username if session.user_knowledge_base else 'Unknown',
                'timestamp': session.created_at.isoformat(),
                'description': f'{session.user_knowledge_base.username if session.user_knowledge_base else "Unknown"} started: {session.title}'
            }
            for session in recent_sessions
        ]

        # Combine and sort by timestamp
        all_activities = user_activities + doc_activities + session_activities
        all_activities.sort(key=lambda x: x['timestamp'], reverse=True)

        # Return top 50
        return JsonResponse({'activities': all_activities[:50]})

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch recent activity',
            'detail': str(e)
        }, status=500)


# ==============================
# USER MANAGEMENT
# ==============================

@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def list_users(request):
    """
    Get paginated list of all users.

    GET /chatlog/admin/users/?page=1&search=john&page_size=20
    """
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '').strip()

        # Base query (exclude staff)
        users_query = User.objects.filter(is_staff=False)

        # Apply search filter
        if search:
            users_query = users_query.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search)
            )

        # Get total count
        total_count = users_query.count()

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        users = users_query.order_by('-date_joined')[start:end]

        # Build user list with stats
        user_list = []
        for user in users:
            # Get user knowledge base
            kb = UserKnowledgeBase.objects.filter(username=user.username).first()

            # Get user stats
            docs_count = UploadedPDF.objects.filter(user_knowledge_base=kb).count() if kb else 0
            sessions_count = ChatSession.objects.filter(user_knowledge_base=kb).count() if kb else 0

            # Get subscription info
            subscription = getattr(user, 'subscription', None)
            subscription_plan = subscription.plan.name if subscription else 'free'
            credits_remaining = subscription.credits_remaining if subscription else 0

            user_list.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat(),
                'is_active': user.is_active,
                'documents_count': docs_count,
                'sessions_count': sessions_count,
                'subscription_plan': subscription_plan,
                'credits_remaining': credits_remaining,
            })

        return JsonResponse({
            'users': user_list,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch users',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_user_detail(request, user_id):
    """
    Get detailed information about a specific user.

    GET /chatlog/admin/users/<user_id>/
    """
    try:
        user = User.objects.get(id=user_id)
        subscription = getattr(user, 'subscription', None)
        kb = UserKnowledgeBase.objects.filter(username=user.username).first()

        # Get user's documents
        documents = UploadedPDF.objects.filter(user_knowledge_base=kb) if kb else []
        docs_list = [
            {
                'id': doc.id,
                'filename': doc.filename,
                'size': doc.file_size if hasattr(doc, 'file_size') else 0,
                'created_at': doc.uploaded_at.isoformat() if hasattr(doc, 'uploaded_at') else '',
            }
            for doc in documents
        ]

        # Get user's sessions
        sessions = ChatSession.objects.filter(user_knowledge_base=kb).order_by('-created_at')[:10] if kb else []
        sessions_list = [
            {
                'id': session.session_id,
                'title': session.title,
                'created_at': session.created_at.isoformat(),
            }
            for session in sessions
        ]

        return JsonResponse({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'date_joined': user.date_joined.isoformat(),
                'is_active': user.is_active,
            },
            'subscription': {
                'plan': subscription.plan.name if subscription else 'free',
                'credits_remaining': subscription.credits_remaining if subscription else 0,
                'credits_total': subscription.plan.credit_limit if subscription else 0,
                'billing_period_start': subscription.current_period_start.isoformat() if subscription else None,
                'billing_period_end': subscription.current_period_end.isoformat() if subscription and subscription.current_period_end else None,
            },
            'documents': docs_list,
            'recent_sessions': sessions_list,
            'stats': {
                'total_documents': len(docs_list),
                'total_sessions': ChatSession.objects.filter(user_knowledge_base=kb).count() if kb else 0,
                'total_messages': ChatMessage.objects.filter(session__user_knowledge_base=kb).count() if kb else 0,
            }
        })

    except User.DoesNotExist:
        return JsonResponse({
            'error': 'User not found',
            'detail': f'No user with ID {user_id} exists.'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user details',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["PATCH"])
def update_user_subscription(request, user_id):
    """
    Update a user's subscription plan.

    PATCH /chatlog/admin/users/<user_id>/subscription/
    Body: {"subscription_plan": "premium"}
    """
    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)
        subscription_plan = data.get('subscription_plan')

        if not subscription_plan:
            return JsonResponse({
                'error': 'Missing subscription plan',
                'detail': 'subscription_plan is required.'
            }, status=400)

        # Get the plan object
        try:
            plan = SubscriptionPlan.objects.get(name=subscription_plan)
        except SubscriptionPlan.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid subscription plan',
                'detail': f'Subscription plan "{subscription_plan}" does not exist.'
            }, status=400)

        # Get or create user subscription
        subscription, created = UserSubscription.objects.get_or_create(
            user=user,
            defaults={'plan': plan}
        )

        # Update subscription plan if it already existed
        old_plan = subscription.plan.name
        if not created:
            subscription.plan = plan
            subscription.save()

        return JsonResponse({
            'success': True,
            'message': f'Subscription updated from {old_plan} to {subscription_plan}',
            'subscription': {
                'plan': subscription.plan.name,
                'credits_remaining': subscription.credits_remaining,
                'credits_total': subscription.plan.credit_limit,
            }
        })

    except User.DoesNotExist:
        return JsonResponse({
            'error': 'User not found',
            'detail': f'No user with ID {user_id} exists.'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON',
            'detail': 'Request body must be valid JSON.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to update subscription',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["POST"])
def adjust_user_credits(request, user_id):
    """
    Adjust a user's credits (add or subtract).

    POST /chatlog/admin/users/<user_id>/credits/
    Body: {"amount": 100, "operation": "add"} or {"amount": 50, "operation": "subtract"}
    """
    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)
        amount = data.get('amount')
        operation = data.get('operation', 'add')

        if amount is None:
            return JsonResponse({
                'error': 'Missing amount',
                'detail': 'amount is required.'
            }, status=400)

        if operation not in ['add', 'subtract']:
            return JsonResponse({
                'error': 'Invalid operation',
                'detail': 'operation must be either "add" or "subtract".'
            }, status=400)

        # Get user subscription
        subscription = getattr(user, 'subscription', None)
        if not subscription:
            # Get default plan
            default_plan = SubscriptionPlan.objects.filter(is_default=True).first()
            if not default_plan:
                default_plan = SubscriptionPlan.objects.filter(name='free').first()

            if not default_plan:
                return JsonResponse({
                    'error': 'No subscription found',
                    'detail': 'User has no subscription and no default plan exists.'
                }, status=400)

            subscription = UserSubscription.objects.create(user=user, plan=default_plan)

        # Adjust credits (note: credits_used is what's stored, credits_remaining is calculated)
        old_credits_remaining = subscription.credits_remaining

        if operation == 'add':
            # Adding credits means reducing credits_used
            subscription.credits_used = max(0, subscription.credits_used - amount)
        else:  # subtract
            # Subtracting credits means increasing credits_used
            subscription.credits_used += amount

        subscription.save()

        return JsonResponse({
            'success': True,
            'message': f'Credits {"added" if operation == "add" else "subtracted"}: {amount}',
            'credits': {
                'old': old_credits_remaining,
                'new': subscription.credits_remaining,
                'total': subscription.plan.credit_limit,
            }
        })

    except User.DoesNotExist:
        return JsonResponse({
            'error': 'User not found',
            'detail': f'No user with ID {user_id} exists.'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON',
            'detail': 'Request body must be valid JSON.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to adjust credits',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["DELETE"])
def delete_user(request, user_id):
    """
    Delete a user account.

    DELETE /chatlog/admin/users/<user_id>/
    """
    try:
        user = User.objects.get(id=user_id)
        username = user.username
        user.delete()

        return JsonResponse({
            'success': True,
            'message': f'User {username} has been deleted.'
        })

    except User.DoesNotExist:
        return JsonResponse({
            'error': 'User not found',
            'detail': f'No user with ID {user_id} exists.'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to delete user',
            'detail': str(e)
        }, status=500)


# ==============================
# DOCUMENT MANAGEMENT  
# ==============================

@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def list_all_documents(request):
    """
    List all documents across all users.
    
    GET /chatlog/admin/documents/?page=1&page_size=20&search=&user_id=
    """
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        search = request.GET.get('search', '').strip()
        user_id = request.GET.get('user_id', '').strip()
        
        # Base query - get all documents
        documents = UploadedPDF.objects.all().select_related('user_knowledge_base')
        
        # Filter by search query (filename or username)
        if search:
            documents = documents.filter(
                Q(filename__icontains=search) |
                Q(user_knowledge_base__username__icontains=search)
            )
        
        # Filter by specific user
        if user_id:
            user_kb = UserKnowledgeBase.objects.filter(user__id=user_id).first()
            if user_kb:
                documents = documents.filter(user_knowledge_base=user_kb)
        
        # Get total count
        total_count = documents.count()
        
        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        documents = documents.order_by('-uploaded_at')[start:end]
        
        # Build document list
        doc_list = []
        for doc in documents:
            doc_list.append({
                'id': doc.id,
                'filename': doc.filename,
                'username': doc.user_knowledge_base.username if doc.user_knowledge_base else 'Unknown',
                'file_size': doc.file_size,
                'chunks_count': doc.chunks_count,
                'status': doc.status,
                'uploaded_at': doc.uploaded_at.isoformat(),
            })
        
        return JsonResponse({
            'documents': doc_list,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
        })
    
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch documents',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["DELETE"])
def delete_document(request, doc_id):
    """
    Delete a document.
    
    DELETE /chatlog/admin/documents/<doc_id>/delete/
    """
    try:
        doc = UploadedPDF.objects.get(id=doc_id)
        filename = doc.filename
        doc.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Document {filename} has been deleted.'
        })
    
    except UploadedPDF.DoesNotExist:
        return JsonResponse({
            'error': 'Document not found',
            'detail': f'No document with ID {doc_id} exists.'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to delete document',
            'detail': str(e)
        }, status=500)

# ==============================
# SUBSCRIPTION PLAN MANAGEMENT
# ==============================

@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def list_subscription_plans(request):
    """
    List all subscription plans.
    
    GET /chatlog/admin/plans/
    """
    try:
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')
        
        plan_list = []
        for plan in plans:
            # Count subscribers
            subscriber_count = UserSubscription.objects.filter(plan=plan, status='active').count()
            
            plan_list.append({
                'id': str(plan.id),
                'name': plan.name,
                'display_name': plan.display_name,
                'description': plan.description,
                'credit_limit': plan.credit_limit,
                'pdf_limit': plan.pdf_limit,
                'price_monthly': float(plan.price_monthly),
                'price_yearly': float(plan.price_yearly),
                'features': plan.features,
                'is_active': plan.is_active,
                'is_default': plan.is_default,
                'subscriber_count': subscriber_count,
                'created_at': plan.created_at.isoformat(),
            })
        
        return JsonResponse({'plans': plan_list})
    
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch subscription plans',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_subscription_plan(request, plan_id):
    """
    Get details for a specific subscription plan.
    
    GET /chatlog/admin/plans/<plan_id>/
    """
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
        subscriber_count = UserSubscription.objects.filter(plan=plan, status='active').count()
        
        return JsonResponse({
            'plan': {
                'id': str(plan.id),
                'name': plan.name,
                'display_name': plan.display_name,
                'description': plan.description,
                'credit_limit': plan.credit_limit,
                'pdf_limit': plan.pdf_limit,
                'price_monthly': float(plan.price_monthly),
                'price_yearly': float(plan.price_yearly),
                'features': plan.features,
                'is_active': plan.is_active,
                'is_default': plan.is_default,
                'subscriber_count': subscriber_count,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat(),
            }
        })
    
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch plan details',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["POST"])
def create_subscription_plan(request):
    """
    Create a new subscription plan.
    
    POST /chatlog/admin/plans/create/
    Body: {
        "name": "pro",
        "display_name": "Pro Plan",
        "description": "...",
        "credit_limit": 10000,
        "pdf_limit": 10,
        "price_monthly": 29.99,
        "price_yearly": 299.99,
        "features": ["feature1", "feature2"]
    }
    """
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['name', 'display_name', 'credit_limit', 'pdf_limit']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)
        
        # Create the plan
        plan = SubscriptionPlan.objects.create(
            name=data['name'],
            display_name=data['display_name'],
            description=data.get('description', ''),
            credit_limit=data['credit_limit'],
            pdf_limit=data['pdf_limit'],
            price_monthly=data.get('price_monthly', 0),
            price_yearly=data.get('price_yearly', 0),
            features=data.get('features', []),
            is_default=data.get('is_default', False)
        )
        
        return JsonResponse({
            'success': True,
            'plan': {
                'id': str(plan.id),
                'name': plan.name,
                'display_name': plan.display_name,
                'description': plan.description,
                'credit_limit': plan.credit_limit,
                'pdf_limit': plan.pdf_limit,
                'price_monthly': float(plan.price_monthly),
                'price_yearly': float(plan.price_yearly),
                'features': plan.features,
                'is_default': plan.is_default,
            }
        }, status=201)
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to create plan',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["PUT", "PATCH"])
def update_subscription_plan(request, plan_id):
    """
    Update a subscription plan.
    
    PATCH /chatlog/admin/plans/<plan_id>/update/
    Body: { "price_monthly": 39.99, ... }
    """
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
        data = json.loads(request.body)
        
        # Update allowed fields
        allowed_fields = [
            'display_name', 'description', 'credit_limit', 'pdf_limit',
            'price_monthly', 'price_yearly', 'features', 'is_active', 'is_default'
        ]
        
        for field in allowed_fields:
            if field in data:
                setattr(plan, field, data[field])
        
        plan.save()
        
        return JsonResponse({
            'success': True,
            'plan': {
                'id': str(plan.id),
                'name': plan.name,
                'display_name': plan.display_name,
                'description': plan.description,
                'credit_limit': plan.credit_limit,
                'pdf_limit': plan.pdf_limit,
                'price_monthly': float(plan.price_monthly),
                'price_yearly': float(plan.price_yearly),
                'features': plan.features,
                'is_active': plan.is_active,
                'is_default': plan.is_default,
            }
        })
    
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to update plan',
            'detail': str(e)
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["DELETE"])
def delete_subscription_plan(request, plan_id):
    """
    Delete a subscription plan (soft delete by setting is_active=False).
    
    DELETE /chatlog/admin/plans/<plan_id>/delete/
    """
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
        
        # Check if any users are subscribed
        subscriber_count = UserSubscription.objects.filter(plan=plan, status='active').count()
        if subscriber_count > 0:
            return JsonResponse({
                'error': 'Cannot delete plan with active subscribers',
                'detail': f'{subscriber_count} users are currently subscribed to this plan.'
            }, status=400)
        
        # Soft delete
        plan.is_active = False
        plan.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Plan "{plan.display_name}" has been deactivated.'
        })

    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to delete plan',
            'detail': str(e)
        }, status=500)


# ==============================
# ANALYTICS ENDPOINTS
# ==============================

@require_staff
@require_http_methods(["GET"])
def revenue_trends(request):
    """
    Get monthly revenue trends for the last 12 months.

    GET /chatlog/admin/analytics/revenue-trends/

    Returns revenue data broken down by subscription plan.
    """
    try:
        # Calculate date 12 months ago
        twelve_months_ago = timezone.now() - timedelta(days=365)

        # Get all active subscriptions with their plan details
        subscriptions = UserSubscription.objects.filter(
            created_at__gte=twelve_months_ago
        ).select_related('plan', 'user')

        # Group by month and plan
        monthly_data = {}
        for sub in subscriptions:
            month_key = sub.created_at.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = {}

            plan_name = sub.plan.display_name
            if plan_name not in monthly_data[month_key]:
                monthly_data[month_key][plan_name] = 0

            # Add revenue (assuming price is per month)
            monthly_data[month_key][plan_name] += float(sub.plan.price_monthly)

        # Convert to array format for charts
        revenue_data = []
        for month, plans in sorted(monthly_data.items()):
            data_point = {'month': month}
            total = 0
            for plan, revenue in plans.items():
                data_point[plan] = revenue
                total += revenue
            data_point['total'] = total
            revenue_data.append(data_point)

        return JsonResponse({
            'success': True,
            'data': revenue_data
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch revenue trends',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def user_activity_metrics(request):
    """
    Get user activity metrics for the last 30 days.

    GET /chatlog/admin/analytics/user-activity/

    Returns daily active users, sessions, and messages.
    """
    try:
        thirty_days_ago = timezone.now() - timedelta(days=30)

        # Get daily session counts
        daily_sessions = ChatSession.objects.filter(
            created_at__gte=thirty_days_ago
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            sessions=Count('id'),
            users=Count('user_knowledge_base', distinct=True)
        ).order_by('date')

        # Get daily message counts
        daily_messages = ChatMessage.objects.filter(
            created_at__gte=thirty_days_ago
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            messages=Count('id')
        ).order_by('date')

        # Combine data
        activity_data = []
        messages_dict = {item['date'].isoformat(): item['messages'] for item in daily_messages}

        for item in daily_sessions:
            date_str = item['date'].isoformat()
            activity_data.append({
                'date': date_str,
                'active_users': item['users'],
                'sessions': item['sessions'],
                'messages': messages_dict.get(date_str, 0)
            })

        return JsonResponse({
            'success': True,
            'data': activity_data
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user activity metrics',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def subscription_distribution(request):
    """
    Get subscription distribution by plan.

    GET /chatlog/admin/analytics/subscription-distribution/

    Returns subscriber count grouped by plan for pie chart.
    """
    try:
        # Get active subscriptions grouped by plan
        distribution = UserSubscription.objects.filter(
            status='active'
        ).values(
            'plan__display_name',
            'plan__price_monthly'
        ).annotate(
            count=Count('id')
        ).order_by('-count')

        # Format for chart
        distribution_data = []
        total_subscribers = 0
        total_revenue = 0

        for item in distribution:
            count = item['count']
            price = float(item['plan__price_monthly'])
            revenue = count * price

            total_subscribers += count
            total_revenue += revenue

            distribution_data.append({
                'plan': item['plan__display_name'],
                'subscribers': count,
                'revenue': revenue,
                'price': price
            })

        # Calculate percentages
        for item in distribution_data:
            item['percentage'] = (item['subscribers'] / total_subscribers * 100) if total_subscribers > 0 else 0

        return JsonResponse({
            'success': True,
            'data': distribution_data,
            'summary': {
                'total_subscribers': total_subscribers,
                'total_monthly_revenue': total_revenue,
                'arr': total_revenue * 12  # Annual Recurring Revenue
            }
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch subscription distribution',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def system_health_metrics(request):
    """
    Get system health metrics.

    GET /chatlog/admin/analytics/system-health/

    Returns real-time system metrics.
    """
    try:
        from django.db import connection
        import time

        # Measure database response time
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_response_time = (time.time() - start_time) * 1000  # Convert to ms

        # Get error rate (messages with errors in last hour)
        one_hour_ago = timezone.now() - timedelta(hours=1)
        total_messages = ChatMessage.objects.filter(
            created_at__gte=one_hour_ago
        ).count()

        # Assuming we track errors in feedback or have an error field
        # For now, use a placeholder calculation
        error_rate = 0.5  # 0.5% placeholder

        # Get storage usage
        total_documents = UploadedPDF.objects.count()
        total_foundation_docs = FoundationDocument.objects.count()

        # Calculate storage (sum of file sizes)
        user_storage = UploadedPDF.objects.aggregate(
            total=Sum('file_size')
        )['total'] or 0

        foundation_storage = FoundationDocument.objects.aggregate(
            total=Sum('file_size')
        )['total'] or 0

        total_storage_mb = (user_storage + foundation_storage) / (1024 * 1024)

        # Active sessions in last 24 hours
        active_sessions = ChatSession.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()

        return JsonResponse({
            'success': True,
            'metrics': {
                'db_response_time_ms': round(db_response_time, 2),
                'error_rate_percent': error_rate,
                'storage_used_mb': round(total_storage_mb, 2),
                'active_sessions_24h': active_sessions,
                'total_documents': total_documents + total_foundation_docs,
                'uptime_status': 'healthy',
                'last_updated': timezone.now().isoformat()
            }
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch system health metrics',
            'detail': str(e)
        }, status=500)


# ==============================
# USER DETAIL ENDPOINTS
# ==============================

@require_staff
@require_http_methods(["GET"])
def user_activity_history(request, user_id):
    """
    Get user activity history including login times and actions.

    GET /chatlog/admin/users/<uuid:user_id>/activity/

    Returns timeline of user activities.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get chat sessions as activity
        sessions = ChatSession.objects.filter(
            user_knowledge_base__user=user
        ).order_by('-created_at')[:50]

        # Get document uploads as activity
        documents = UploadedPDF.objects.filter(
            user_knowledge_base__user=user
        ).order_by('-uploaded_at')[:50]

        # Combine and sort activities
        activities = []

        for session in sessions:
            message_count = ChatMessage.objects.filter(session=session).count()
            activities.append({
                'type': 'chat_session',
                'timestamp': session.created_at.isoformat(),
                'description': f'Started chat session: {session.title}',
                'details': f'{message_count} messages',
                'session_id': str(session.id)
            })

        for doc in documents:
            activities.append({
                'type': 'document_upload',
                'timestamp': doc.uploaded_at.isoformat(),
                'description': f'Uploaded document: {doc.filename}',
                'details': f'{doc.file_size / 1024:.1f} KB',
                'document_id': doc.id
            })

        # Sort by timestamp descending
        activities.sort(key=lambda x: x['timestamp'], reverse=True)

        return JsonResponse({
            'success': True,
            'activities': activities[:100],  # Limit to 100 most recent
            'user': {
                'username': user.username,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
        })

    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user activity',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def user_usage_analytics(request, user_id):
    """
    Get user usage analytics including credit usage and feature stats.

    GET /chatlog/admin/users/<uuid:user_id>/usage/

    Returns usage metrics over time.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get subscription info
        try:
            subscription = UserSubscription.objects.get(user=user, status='active')
            plan_info = {
                'plan_name': subscription.plan.display_name,
                'price': float(subscription.plan.price),
                'credits_per_month': subscription.plan.credits_per_month,
                'start_date': subscription.created_at.isoformat(),
                'status': subscription.status
            }
        except UserSubscription.DoesNotExist:
            plan_info = None

        # Get message count over time (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)

        daily_messages = ChatMessage.objects.filter(
            session__user=user,
            created_at__gte=thirty_days_ago
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')

        message_usage = [{
            'date': item['date'].isoformat(),
            'messages': item['count']
        } for item in daily_messages]

        # Get feature usage stats
        total_sessions = ChatSession.objects.filter(user=user).count()
        total_messages = ChatMessage.objects.filter(session__user=user).count()
        total_documents = UploadedPDF.objects.filter(user_kb__user=user).count()

        # Get current credit info
        try:
            subscription = UserSubscription.objects.get(user=user, status='active')
            credits_remaining = subscription.credits_remaining
            credits_info = {
                'current_balance': credits_remaining,
                'total_allocated': subscription.plan.credit_limit,
                'usage_percentage': (
                    subscription.credits_used / subscription.plan.credit_limit * 100
                ) if subscription.plan.credit_limit > 0 else 0
            }
        except UserSubscription.DoesNotExist:
            credits_info = {'current_balance': 0, 'total_allocated': 0, 'usage_percentage': 0}

        return JsonResponse({
            'success': True,
            'plan': plan_info,
            'message_usage': message_usage,
            'feature_stats': {
                'total_sessions': total_sessions,
                'total_messages': total_messages,
                'total_documents': total_documents,
                'avg_messages_per_session': round(total_messages / total_sessions, 1) if total_sessions > 0 else 0
            },
            'credits': credits_info
        })

    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user usage analytics',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def user_billing_info(request, user_id):
    """
    Get user billing information including payment history.

    GET /chatlog/admin/users/<uuid:user_id>/billing/

    Returns billing history and subscription changes.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get current subscription
        try:
            current_sub = UserSubscription.objects.get(user=user, status='active')
            credits_remaining = current_sub.credits_remaining
            current_subscription = {
                'plan_name': current_sub.plan.display_name,
                'price': float(current_sub.plan.price_monthly),
                'status': current_sub.status,
                'start_date': current_sub.created_at.isoformat(),
                'current_period_start': current_sub.current_period_start.isoformat() if current_sub.current_period_start else None,
                'current_period_end': current_sub.current_period_end.isoformat() if current_sub.current_period_end else None,
                'credits_remaining': credits_remaining
            }
        except UserSubscription.DoesNotExist:
            current_subscription = None

        # Get all subscriptions (history)
        all_subscriptions = UserSubscription.objects.filter(
            user=user
        ).select_related('plan').order_by('-created_at')

        subscription_history = []
        for sub in all_subscriptions:
            subscription_history.append({
                'id': str(sub.id),
                'plan_name': sub.plan.display_name,
                'price': float(sub.plan.price_monthly),
                'status': sub.status,
                'start_date': sub.created_at.isoformat(),
                'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
                'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
                'cancelled_at': sub.cancelled_at.isoformat() if sub.cancelled_at else None
            })

        # Calculate lifetime value
        lifetime_value = sum(
            float(sub.plan.price) for sub in all_subscriptions if sub.status == 'active'
        )

        return JsonResponse({
            'success': True,
            'current_subscription': current_subscription,
            'subscription_history': subscription_history,
            'billing_summary': {
                'lifetime_value': lifetime_value,
                'total_subscriptions': all_subscriptions.count(),
                'member_since': user.date_joined.isoformat()
            }
        })

    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user billing info',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["GET"])
def user_documents_list(request, user_id):
    """
    Get list of user's uploaded documents.

    GET /chatlog/admin/users/<uuid:user_id>/documents/

    Returns all documents uploaded by the user.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get user's knowledge base
        try:
            user_kb = UserKnowledgeBase.objects.get(user=user)
            documents = UploadedPDF.objects.filter(
                user_knowledge_base=user_kb
            ).order_by('-uploaded_at')

            documents_list = []
            for doc in documents:
                documents_list.append({
                    'id': doc.id,
                    'filename': doc.filename,
                    'file_size': doc.file_size,
                    'file_size_mb': round(doc.file_size / (1024 * 1024), 2),
                    'chunks_count': doc.chunks_count,
                    'status': doc.status,
                    'uploaded_at': doc.uploaded_at.isoformat()
                })

            total_storage = sum(doc.file_size for doc in documents)

            return JsonResponse({
                'success': True,
                'documents': documents_list,
                'summary': {
                    'total_documents': documents.count(),
                    'total_storage_mb': round(total_storage / (1024 * 1024), 2),
                    'processed_documents': documents.filter(status='processed').count(),
                    'failed_documents': documents.filter(status='failed').count()
                }
            })

        except UserKnowledgeBase.DoesNotExist:
            return JsonResponse({
                'success': True,
                'documents': [],
                'summary': {
                    'total_documents': 0,
                    'total_storage_mb': 0,
                    'processed_documents': 0,
                    'failed_documents': 0
                }
            })

    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch user documents',
            'detail': str(e)
        }, status=500)


# ==============================
# FEEDBACK MANAGEMENT
# ==============================

@require_staff
@require_http_methods(["GET"])
def admin_feedback_list(request):
    """
    Get all user feedback with pagination and filtering.

    GET /chatlog/admin/feedback/
    Query params:
      - page: Page number (default 1)
      - page_size: Items per page (default 50)
      - feedback_type: Filter by type (thumbs_up, thumbs_down, save_note, copy)
      - content_type: Filter by content type (summary, chat_response)
      - username: Filter by username
    """
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        feedback_type = request.GET.get('feedback_type')
        content_type = request.GET.get('content_type')
        username = request.GET.get('username')

        # Build query
        feedbacks = UserFeedback.objects.select_related('user_knowledge_base').all()

        if feedback_type:
            feedbacks = feedbacks.filter(feedback_type=feedback_type)
        if content_type:
            feedbacks = feedbacks.filter(content_type=content_type)
        if username:
            feedbacks = feedbacks.filter(user_knowledge_base__username__icontains=username)

        # Order by most recent
        feedbacks = feedbacks.order_by('-created_at')

        # Calculate totals
        total = feedbacks.count()
        total_pages = (total + page_size - 1) // page_size

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        page_feedbacks = feedbacks[start:end]

        # Serialize
        feedback_list = []
        for fb in page_feedbacks:
            feedback_list.append({
                'id': fb.id,
                'username': fb.user_knowledge_base.username,
                'feedback_type': fb.feedback_type,
                'content_type': fb.content_type,
                'content_preview': fb.content_preview[:200] + '...' if fb.content_preview and len(fb.content_preview) > 200 else fb.content_preview,
                'comment': fb.comment,
                'created_at': fb.created_at.isoformat(),
            })

        # Get stats
        stats = {
            'total': UserFeedback.objects.count(),
            'thumbs_up': UserFeedback.objects.filter(feedback_type='thumbs_up').count(),
            'thumbs_down': UserFeedback.objects.filter(feedback_type='thumbs_down').count(),
            'save_note': UserFeedback.objects.filter(feedback_type='save_note').count(),
            'copy': UserFeedback.objects.filter(feedback_type='copy').count(),
        }

        return JsonResponse({
            'success': True,
            'feedbacks': feedback_list,
            'stats': stats,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
        })

    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch feedback',
            'detail': str(e)
        }, status=500)


@require_staff
@require_http_methods(["DELETE"])
def admin_feedback_delete(request, feedback_id):
    """
    Delete a feedback entry.

    DELETE /chatlog/admin/feedback/<id>/delete/
    """
    try:
        feedback = UserFeedback.objects.get(id=feedback_id)
        feedback.delete()
        return JsonResponse({
            'success': True,
            'message': 'Feedback deleted successfully'
        })
    except UserFeedback.DoesNotExist:
        return JsonResponse({'error': 'Feedback not found'}, status=404)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to delete feedback',
            'detail': str(e)
        }, status=500)


# ==============================
# AI MODEL CONFIGURATION
# ==============================

@require_staff
@require_http_methods(["GET"])
def get_model_config(request):
    """
    Get available AI models and current configuration.

    GET /chatlog/admin/models/
    
    Returns list of available models and which one is currently active.
    """
    try:
        from .langgraph_agent import get_available_models, get_current_model, AVAILABLE_MODELS
        
        current_model = get_current_model()
        available_models = get_available_models()
        
        # Add current status to the models list
        for model in available_models:
            model['is_current'] = model['id'] == current_model
        
        return JsonResponse({
            'success': True,
            'current_model': current_model,
            'current_model_name': AVAILABLE_MODELS.get(current_model, {}).get('name', 'Unknown'),
            'models': available_models,
        })
    
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to fetch model configuration',
            'detail': str(e)
        }, status=500)


@require_staff
@csrf_exempt
@require_http_methods(["POST"])
def set_model_config(request):
    """
    Set the active AI model.

    POST /chatlog/admin/models/set/
    Body: {"model_id": "gpt-4o"}
    
    Changes the AI model used for all chat requests.
    """
    try:
        from .langgraph_agent import set_current_model, get_available_models, AVAILABLE_MODELS
        from .views import _agent_cache
        
        data = json.loads(request.body)
        model_id = data.get('model_id')
        
        if not model_id:
            return JsonResponse({'error': 'model_id is required'}, status=400)
        
        # Validate model exists
        if model_id not in AVAILABLE_MODELS:
            return JsonResponse({
                'error': f'Unknown model: {model_id}',
                'available': list(AVAILABLE_MODELS.keys())
            }, status=400)
        
        # Set the new model
        set_current_model(model_id)
        
        # Clear the agent cache so new requests use the new model
        _agent_cache.clear()
        print(f"[Admin] Cleared agent cache after model change to {model_id}")
        
        return JsonResponse({
            'success': True,
            'message': f'Model changed to {AVAILABLE_MODELS[model_id]["name"]}',
            'current_model': model_id,
        })
    
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to set model',
            'detail': str(e)
        }, status=500)


# ==============================
# VECTOR CHUNKS MANAGEMENT
# ==============================

@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_all_chunks(request):
    """
    Get all vector chunks from the database with pagination.

    GET /chatlog/admin/chunks/
    Query params:
    - page: Page number (default 1)
    - page_size: Items per page (default 50, max 100)
    - source: Filter by source ('foundation', 'user', or 'all')
    - search: Search in chunk content
    - collection: Filter by specific collection name
    """
    try:
        from django.db import connection

        # Parse query params
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 50)), 100)
        source = request.GET.get('source', 'all')  # 'foundation', 'user', 'all'
        search = request.GET.get('search', '').strip()
        collection_filter = request.GET.get('collection', '').strip()

        offset = (page - 1) * page_size

        chunks = []
        total_count = 0
        collections = []

        with connection.cursor() as cursor:
            # Get all collections first
            cursor.execute("""
                SELECT c.uuid, c.name, COUNT(e.uuid) as chunk_count
                FROM langchain_pg_collection c
                LEFT JOIN langchain_pg_embedding e ON e.collection_id = c.uuid
                GROUP BY c.uuid, c.name
                ORDER BY c.name
            """)
            collections = [
                {
                    'uuid': str(row[0]),
                    'name': row[1],
                    'chunk_count': row[2],
                    'is_foundation': row[1] == 'foundation_mining_kb'
                }
                for row in cursor.fetchall()
            ]

            # Build WHERE clause based on filters
            where_clauses = []
            params = []

            if source == 'foundation':
                where_clauses.append("c.name = 'foundation_mining_kb'")
            elif source == 'user':
                where_clauses.append("c.name != 'foundation_mining_kb'")

            if collection_filter:
                where_clauses.append("c.name = %s")
                params.append(collection_filter)

            if search:
                where_clauses.append("e.document ILIKE %s")
                params.append(f'%{search}%')

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            # Get total count
            count_query = f"""
                SELECT COUNT(*)
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                {where_sql}
            """
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            # Get chunks with pagination
            chunks_query = f"""
                SELECT
                    e.uuid,
                    c.name as collection_name,
                    LEFT(e.document, 500) as content_preview,
                    LENGTH(e.document) as content_length,
                    e.cmetadata
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                {where_sql}
                ORDER BY c.name, e.uuid
                LIMIT %s OFFSET %s
            """
            cursor.execute(chunks_query, params + [page_size, offset])

            for row in cursor.fetchall():
                metadata = row[4] if row[4] else {}
                chunks.append({
                    'id': str(row[0]),
                    'collection': row[1],
                    'is_foundation': row[1] == 'foundation_mining_kb',
                    'content_preview': row[2] + ('...' if row[3] > 500 else ''),
                    'content_length': row[3],
                    'source_file': metadata.get('source', metadata.get('filename', 'Unknown')),
                    'page': metadata.get('page', None),
                    'metadata': metadata
                })

        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size

        return JsonResponse({
            'chunks': chunks,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'collections': collections,
            'filters': {
                'source': source,
                'search': search,
                'collection': collection_filter
            }
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@csrf_exempt
@require_staff
@require_http_methods(["GET"])
def get_chunk_detail(request, chunk_id):
    """
    Get full details of a specific chunk.

    GET /chatlog/admin/chunks/<chunk_id>/
    """
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    e.uuid,
                    c.name as collection_name,
                    e.document,
                    e.cmetadata
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE e.uuid = %s
            """, [chunk_id])

            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Chunk not found'}, status=404)

            metadata = row[3] if row[3] else {}

            return JsonResponse({
                'id': str(row[0]),
                'collection': row[1],
                'is_foundation': row[1] == 'foundation_mining_kb',
                'content': row[2],
                'content_length': len(row[2]),
                'source_file': metadata.get('source', metadata.get('filename', 'Unknown')),
                'page': metadata.get('page', None),
                'metadata': metadata
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
