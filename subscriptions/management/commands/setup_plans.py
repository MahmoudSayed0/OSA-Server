from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan, UserSubscription
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create initial subscription plans and assign to existing users'

    def handle(self, *args, **options):
        self.stdout.write('Setting up subscription plans...')

        # Create Free plan
        free_plan, created = SubscriptionPlan.objects.update_or_create(
            name='free',
            defaults={
                'display_name': 'Free',
                'description': 'Perfect for getting started with safety document management',
                'credit_limit': 1000,
                'pdf_limit': 3,
                'price_monthly': 0,
                'price_yearly': 0,
                'is_default': True,
                'is_active': True,
                'features': [
                    '1,000 credits per month',
                    '3 PDF uploads',
                    'Basic AI chat support',
                    'Standard response time',
                ]
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Free plan'))
        else:
            self.stdout.write(f'Updated Free plan')

        # Create Pro plan
        pro_plan, created = SubscriptionPlan.objects.update_or_create(
            name='pro',
            defaults={
                'display_name': 'Pro',
                'description': 'For professionals who need more power and flexibility',
                'credit_limit': 20000,
                'pdf_limit': 20,
                'price_monthly': 19.99,
                'price_yearly': 199.99,
                'is_default': False,
                'is_active': True,
                'features': [
                    '20,000 credits per month',
                    '20 PDF uploads',
                    'Priority AI responses',
                    'Advanced analytics',
                    'Email support',
                ]
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Pro plan'))
        else:
            self.stdout.write(f'Updated Pro plan')

        # Create Enterprise plan (for future)
        enterprise_plan, created = SubscriptionPlan.objects.update_or_create(
            name='enterprise',
            defaults={
                'display_name': 'Enterprise',
                'description': 'Custom solutions for large organizations',
                'credit_limit': 100000,
                'pdf_limit': 100,
                'price_monthly': 99.99,
                'price_yearly': 999.99,
                'is_default': False,
                'is_active': False,  # Not active yet
                'features': [
                    '100,000 credits per month',
                    '100 PDF uploads',
                    'Dedicated support',
                    'Custom integrations',
                    'Team management',
                    'API access',
                ]
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Enterprise plan (inactive)'))
        else:
            self.stdout.write(f'Updated Enterprise plan')

        # Assign free plan to existing users without subscriptions
        users_without_sub = User.objects.filter(subscription__isnull=True)
        count = 0
        for user in users_without_sub:
            UserSubscription.objects.create(
                user=user,
                plan=free_plan,
                status='active'
            )
            count += 1

        if count > 0:
            self.stdout.write(self.style.SUCCESS(f'Assigned Free plan to {count} existing users'))
        else:
            self.stdout.write('All users already have subscriptions')

        self.stdout.write(self.style.SUCCESS('Subscription plans setup complete!'))
