from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, CreditTransaction


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for subscription plans."""

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'display_name', 'description',
            'credit_limit', 'pdf_limit',
            'price_monthly', 'price_yearly',
            'features', 'is_active'
        ]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for user subscription details."""
    plan = SubscriptionPlanSerializer(read_only=True)
    credits_remaining = serializers.IntegerField(read_only=True)
    pdfs_remaining = serializers.IntegerField(read_only=True)
    is_credits_exhausted = serializers.BooleanField(read_only=True)
    is_pdf_limit_reached = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'plan', 'status',
            'credits_used', 'credits_remaining',
            'pdfs_uploaded', 'pdfs_remaining',
            'is_credits_exhausted', 'is_pdf_limit_reached',
            'current_period_start', 'current_period_end',
            'created_at'
        ]


class UsageStatsSerializer(serializers.Serializer):
    """Serializer for usage statistics."""
    credits_used = serializers.IntegerField()
    credits_remaining = serializers.IntegerField()
    credits_limit = serializers.IntegerField()
    credits_percentage = serializers.FloatField()

    pdfs_uploaded = serializers.IntegerField()
    pdfs_remaining = serializers.IntegerField()
    pdfs_limit = serializers.IntegerField()
    pdfs_percentage = serializers.FloatField()

    current_period_start = serializers.DateTimeField()
    current_period_end = serializers.DateTimeField()
    days_remaining = serializers.IntegerField()

    plan_name = serializers.CharField()
    plan_display_name = serializers.CharField()


class CreditTransactionSerializer(serializers.ModelSerializer):
    """Serializer for credit transactions."""

    class Meta:
        model = CreditTransaction
        fields = [
            'id', 'transaction_type', 'amount',
            'balance_after', 'description', 'metadata',
            'created_at'
        ]


class CheckLimitSerializer(serializers.Serializer):
    """Serializer for limit check requests."""
    action = serializers.ChoiceField(choices=['chat', 'pdf_upload'])
    credits_needed = serializers.IntegerField(required=False, default=0)


class CheckLimitResponseSerializer(serializers.Serializer):
    """Serializer for limit check responses."""
    allowed = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)
    credits_remaining = serializers.IntegerField()
    pdfs_remaining = serializers.IntegerField()
    upgrade_required = serializers.BooleanField()
