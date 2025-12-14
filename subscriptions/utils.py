"""
Utility functions for subscription limit checking.
Use these in other views to enforce limits.
"""

from .models import UserSubscription, CreditTransaction


def get_user_subscription(user):
    """
    Get user's subscription, handling cases where it doesn't exist.
    """
    try:
        subscription = user.subscription

        # Check if period expired and reset if needed
        if subscription.is_period_expired:
            subscription.reset_monthly_usage()

        return subscription
    except (UserSubscription.DoesNotExist, AttributeError):
        return None


def can_use_credits(user, amount=0):
    """
    Check if user has enough credits for an action.
    Returns (bool, error_message)
    """
    subscription = get_user_subscription(user)

    if not subscription:
        return False, "No active subscription"

    if subscription.status != 'active':
        return False, "Subscription is not active"

    if subscription.is_credits_exhausted:
        return False, "Monthly credit limit reached"

    if amount > 0 and subscription.credits_remaining < amount:
        return False, f"Insufficient credits. Need {amount}, have {subscription.credits_remaining}"

    return True, None


def can_upload_pdf(user):
    """
    Check if user can upload more PDFs.
    Returns (bool, error_message)
    """
    subscription = get_user_subscription(user)

    if not subscription:
        return False, "No active subscription"

    if subscription.status != 'active':
        return False, "Subscription is not active"

    if subscription.is_pdf_limit_reached:
        return False, f"PDF limit reached ({subscription.plan.pdf_limit}). Upgrade or delete existing PDFs."

    return True, None


def use_credits(user, amount, action_type='chat', description='', metadata=None):
    """
    Deduct credits from user's subscription.
    Returns (bool, error_message, remaining_credits)
    """
    subscription = get_user_subscription(user)

    if not subscription:
        return False, "No active subscription", 0

    if not subscription.use_credits(amount):
        return False, "Insufficient credits", subscription.credits_remaining

    # Log the transaction
    CreditTransaction.log_usage(
        user=user,
        transaction_type=action_type,
        amount=amount,
        description=description,
        metadata=metadata or {}
    )

    return True, None, subscription.credits_remaining


def increment_pdf_count(user):
    """
    Increment PDF count after successful upload.
    """
    subscription = get_user_subscription(user)
    if subscription:
        subscription.increment_pdf_count()
        return True
    return False


def decrement_pdf_count(user):
    """
    Decrement PDF count after deletion.
    """
    subscription = get_user_subscription(user)
    if subscription:
        subscription.decrement_pdf_count()
        return True
    return False


def get_usage_summary(user):
    """
    Get a quick summary of user's usage.
    """
    subscription = get_user_subscription(user)

    if not subscription:
        return None

    return {
        'plan': subscription.plan.display_name,
        'credits_used': subscription.credits_used,
        'credits_remaining': subscription.credits_remaining,
        'credits_limit': subscription.plan.credit_limit,
        'pdfs_uploaded': subscription.pdfs_uploaded,
        'pdfs_remaining': subscription.pdfs_remaining,
        'pdfs_limit': subscription.plan.pdf_limit,
    }
