from django.db import models
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import relativedelta
import uuid


class SubscriptionPlan(models.Model):
    """
    Defines available subscription plans (Free, Pro, etc.)
    """
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Limits
    credit_limit = models.IntegerField(default=1000, help_text="Monthly credit limit")
    pdf_limit = models.IntegerField(default=3, help_text="Maximum PDFs allowed")

    # Pricing (for future Stripe integration)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Features as JSON for flexibility
    features = models.JSONField(default=list, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Auto-assign to new users")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_plans'
        ordering = ['price_monthly']

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        # Ensure only one default plan
        if self.is_default:
            SubscriptionPlan.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class UserSubscription(models.Model):
    """
    Links a user to their subscription plan with usage tracking.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('past_due', 'Past Due'),
        ('trialing', 'Trialing'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscribers'
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Usage tracking
    credits_used = models.IntegerField(default=0, help_text="Credits used this billing period")
    pdfs_uploaded = models.IntegerField(default=0, help_text="Total PDFs uploaded")

    # Billing period
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # For future Stripe integration
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'user_subscriptions'

    def __str__(self):
        return f"{self.user.email} - {self.plan.display_name}"

    def save(self, *args, **kwargs):
        # Set period end if not set (1 month from start)
        if not self.current_period_end:
            self.current_period_end = self.current_period_start + relativedelta(months=1)
        super().save(*args, **kwargs)

    @property
    def credits_remaining(self):
        """Calculate remaining credits for the current period."""
        return max(0, self.plan.credit_limit - self.credits_used)

    @property
    def pdfs_remaining(self):
        """Calculate remaining PDF slots."""
        return max(0, self.plan.pdf_limit - self.pdfs_uploaded)

    @property
    def is_credits_exhausted(self):
        """Check if credits are exhausted."""
        return self.credits_used >= self.plan.credit_limit

    @property
    def is_pdf_limit_reached(self):
        """Check if PDF limit is reached."""
        return self.pdfs_uploaded >= self.plan.pdf_limit

    @property
    def is_period_expired(self):
        """Check if the current billing period has expired."""
        return timezone.now() > self.current_period_end if self.current_period_end else False

    def reset_monthly_usage(self):
        """Reset credits for new billing period."""
        self.credits_used = 0
        self.current_period_start = timezone.now()
        self.current_period_end = self.current_period_start + relativedelta(months=1)
        self.save()

    def use_credits(self, amount):
        """
        Deduct credits from the user's balance.
        Returns True if successful, False if insufficient credits.
        """
        # Check if period expired and reset if needed
        if self.is_period_expired:
            self.reset_monthly_usage()

        if self.credits_used + amount > self.plan.credit_limit:
            return False

        self.credits_used += amount
        self.save(update_fields=['credits_used', 'updated_at'])
        return True

    def can_upload_pdf(self):
        """Check if user can upload more PDFs."""
        return self.pdfs_uploaded < self.plan.pdf_limit

    def increment_pdf_count(self):
        """Increment PDF count after successful upload."""
        self.pdfs_uploaded += 1
        self.save(update_fields=['pdfs_uploaded', 'updated_at'])

    def decrement_pdf_count(self):
        """Decrement PDF count after deletion."""
        if self.pdfs_uploaded > 0:
            self.pdfs_uploaded -= 1
            self.save(update_fields=['pdfs_uploaded', 'updated_at'])


class CreditTransaction(models.Model):
    """
    Tracks all credit transactions for audit and history.
    """
    TRANSACTION_TYPES = [
        ('chat', 'Chat Message'),
        ('pdf_upload', 'PDF Upload'),
        ('pdf_process', 'PDF Processing'),
        ('refund', 'Refund'),
        ('bonus', 'Bonus Credits'),
        ('reset', 'Monthly Reset'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credit_transactions'
    )

    # Transaction details
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.IntegerField(help_text="Positive for credits added, negative for credits used")
    balance_after = models.IntegerField(help_text="User's credit balance after this transaction")

    # Context
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional context (tokens used, session_id, etc.)")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'credit_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['transaction_type']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.transaction_type}: {self.amount}"

    @classmethod
    def log_usage(cls, user, transaction_type, amount, description='', metadata=None):
        """
        Log a credit transaction and update user's subscription.
        Amount should be positive for usage (will be stored as negative).
        """
        subscription = getattr(user, 'subscription', None)
        if not subscription:
            return None

        # For usage, amount is positive input but stored as negative
        actual_amount = -abs(amount) if transaction_type not in ['refund', 'bonus', 'reset'] else abs(amount)

        # Calculate balance after
        balance_after = subscription.credits_remaining + actual_amount if actual_amount > 0 else subscription.credits_remaining

        transaction = cls.objects.create(
            user=user,
            transaction_type=transaction_type,
            amount=actual_amount,
            balance_after=max(0, balance_after),
            description=description,
            metadata=metadata or {}
        )

        return transaction
