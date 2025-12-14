from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from .models import SubscriptionPlan, UserSubscription


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_subscription(sender, instance, created, **kwargs):
    """
    Auto-assign free plan to new users.
    """
    if created:
        # Get the default (free) plan
        default_plan = SubscriptionPlan.objects.filter(is_default=True, is_active=True).first()

        if not default_plan:
            # Fallback: get or create the free plan
            default_plan, _ = SubscriptionPlan.objects.get_or_create(
                name='free',
                defaults={
                    'display_name': 'Free',
                    'description': 'Free tier with basic features',
                    'credit_limit': 1000,
                    'pdf_limit': 3,
                    'price_monthly': 0,
                    'price_yearly': 0,
                    'is_default': True,
                    'features': [
                        '1,000 credits per month',
                        '3 PDF uploads',
                        'Basic chat support',
                    ]
                }
            )

        # Create subscription for the user
        UserSubscription.objects.get_or_create(
            user=instance,
            defaults={
                'plan': default_plan,
                'status': 'active',
            }
        )
