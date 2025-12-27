from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from .models import SubscriptionPlan, UserSubscription, CreditTransaction
from .serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    UsageStatsSerializer,
    CreditTransactionSerializer,
    CheckLimitSerializer,
    CheckLimitResponseSerializer,
)


@api_view(['GET'])
@permission_classes([AllowAny])
def list_plans(request):
    """
    List all available subscription plans.
    """
    plans = SubscriptionPlan.objects.filter(is_active=True)
    serializer = SubscriptionPlanSerializer(plans, many=True)
    return Response({
        'plans': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_subscription(request):
    """
    Get the current user's subscription details.
    """
    try:
        subscription = request.user.subscription

        # Check if period expired and reset if needed
        if subscription.is_period_expired:
            subscription.reset_monthly_usage()

        serializer = UserSubscriptionSerializer(subscription)
        return Response(serializer.data)
    except UserSubscription.DoesNotExist:
        return Response(
            {'error': 'No subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def usage_stats(request):
    """
    Get detailed usage statistics for the current user.
    """
    try:
        subscription = request.user.subscription

        # Check if period expired and reset if needed
        if subscription.is_period_expired:
            subscription.reset_monthly_usage()

        plan = subscription.plan

        # Calculate days remaining in period
        days_remaining = 0
        if subscription.current_period_end:
            delta = subscription.current_period_end - timezone.now()
            days_remaining = max(0, delta.days)

        # Count actual completed PDFs from database (more accurate than counter)
        from chatlog.models import UserKnowledgeBase, UploadedPDF
        actual_pdfs = 0
        try:
            user_kb = UserKnowledgeBase.objects.filter(username=request.user.username).first()
            if user_kb:
                actual_pdfs = UploadedPDF.objects.filter(
                    user_knowledge_base=user_kb,
                    status='completed'
                ).count()
        except Exception:
            actual_pdfs = subscription.pdfs_uploaded  # Fallback to counter

        # Calculate percentages
        credits_percentage = (subscription.credits_used / plan.credit_limit * 100) if plan.credit_limit > 0 else 0
        pdfs_percentage = (actual_pdfs / plan.pdf_limit * 100) if plan.pdf_limit > 0 else 0

        data = {
            'credits_used': subscription.credits_used,
            'credits_remaining': subscription.credits_remaining,
            'credits_limit': plan.credit_limit,
            'credits_percentage': round(credits_percentage, 1),

            'pdfs_uploaded': actual_pdfs,  # Use actual count instead of counter
            'pdfs_remaining': max(0, plan.pdf_limit - actual_pdfs),
            'pdfs_limit': plan.pdf_limit,
            'pdfs_percentage': round(pdfs_percentage, 1),

            'current_period_start': subscription.current_period_start,
            'current_period_end': subscription.current_period_end,
            'days_remaining': days_remaining,

            'plan_name': plan.name,
            'plan_display_name': plan.display_name,
        }

        serializer = UsageStatsSerializer(data)
        return Response(serializer.data)
    except UserSubscription.DoesNotExist:
        return Response(
            {'error': 'No subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    """
    Get credit transaction history for the current user.
    """
    # Get optional query params
    limit = int(request.query_params.get('limit', 50))
    offset = int(request.query_params.get('offset', 0))
    transaction_type = request.query_params.get('type', None)

    transactions = CreditTransaction.objects.filter(user=request.user)

    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)

    total = transactions.count()
    transactions = transactions[offset:offset + limit]

    serializer = CreditTransactionSerializer(transactions, many=True)
    return Response({
        'transactions': serializer.data,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_limit(request):
    """
    Check if a user can perform an action based on their limits.
    Used before chat or PDF upload.
    """
    serializer = CheckLimitSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    action = serializer.validated_data['action']
    credits_needed = serializer.validated_data.get('credits_needed', 0)

    try:
        subscription = request.user.subscription

        # Check if period expired and reset if needed
        if subscription.is_period_expired:
            subscription.reset_monthly_usage()

        response_data = {
            'allowed': True,
            'reason': '',
            'credits_remaining': subscription.credits_remaining,
            'pdfs_remaining': subscription.pdfs_remaining,
            'upgrade_required': False
        }

        if action == 'chat':
            if subscription.is_credits_exhausted:
                response_data['allowed'] = False
                response_data['reason'] = 'You have exhausted your monthly credits. Please upgrade to continue.'
                response_data['upgrade_required'] = True
            elif credits_needed > 0 and subscription.credits_remaining < credits_needed:
                response_data['allowed'] = False
                response_data['reason'] = f'Insufficient credits. You need {credits_needed} but have {subscription.credits_remaining}.'
                response_data['upgrade_required'] = True

        elif action == 'pdf_upload':
            if subscription.is_pdf_limit_reached:
                response_data['allowed'] = False
                response_data['reason'] = f'You have reached your PDF limit ({subscription.plan.pdf_limit}). Please upgrade or delete existing PDFs.'
                response_data['upgrade_required'] = True

        return Response(response_data)

    except UserSubscription.DoesNotExist:
        return Response(
            {'error': 'No subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def use_credits(request):
    """
    Deduct credits for an action (called after successful chat/operation).
    """
    amount = request.data.get('amount', 0)
    action_type = request.data.get('action_type', 'chat')
    description = request.data.get('description', '')
    metadata = request.data.get('metadata', {})

    if amount <= 0:
        return Response(
            {'error': 'Amount must be positive'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        subscription = request.user.subscription

        # Check if period expired and reset if needed
        if subscription.is_period_expired:
            subscription.reset_monthly_usage()

        # Try to use credits
        if subscription.use_credits(amount):
            # Log the transaction
            CreditTransaction.log_usage(
                user=request.user,
                transaction_type=action_type,
                amount=amount,
                description=description,
                metadata=metadata
            )

            return Response({
                'success': True,
                'credits_used': amount,
                'credits_remaining': subscription.credits_remaining
            })
        else:
            return Response({
                'success': False,
                'error': 'Insufficient credits',
                'credits_remaining': subscription.credits_remaining,
                'upgrade_required': True
            }, status=status.HTTP_402_PAYMENT_REQUIRED)

    except UserSubscription.DoesNotExist:
        return Response(
            {'error': 'No subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upgrade_plan(request):
    """
    Upgrade user to a different plan.
    For beta: Just switches the plan without payment.
    Future: Will integrate with Stripe.
    """
    plan_name = request.data.get('plan', None)

    if not plan_name:
        return Response(
            {'error': 'Plan name is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        new_plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return Response(
            {'error': 'Plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        subscription = request.user.subscription
        old_plan = subscription.plan

        # Update the plan
        subscription.plan = new_plan
        subscription.status = 'active'
        subscription.save()

        return Response({
            'success': True,
            'message': f'Successfully upgraded from {old_plan.display_name} to {new_plan.display_name}',
            'new_plan': SubscriptionPlanSerializer(new_plan).data
        })

    except UserSubscription.DoesNotExist:
        return Response(
            {'error': 'No subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )
