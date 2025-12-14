from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, CreditTransaction


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'name', 'credit_limit', 'pdf_limit', 'price_monthly', 'is_active', 'is_default']
    list_filter = ['is_active', 'is_default']
    search_fields = ['name', 'display_name']
    readonly_fields = ['id', 'created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'display_name', 'description')
        }),
        ('Limits', {
            'fields': ('credit_limit', 'pdf_limit')
        }),
        ('Pricing', {
            'fields': ('price_monthly', 'price_yearly')
        }),
        ('Features', {
            'fields': ('features',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_default')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'status', 'credits_used', 'credits_remaining', 'pdfs_uploaded', 'pdfs_remaining', 'current_period_end']
    list_filter = ['status', 'plan']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['id', 'credits_remaining', 'pdfs_remaining', 'created_at', 'updated_at']
    raw_id_fields = ['user']

    fieldsets = (
        (None, {
            'fields': ('user', 'plan', 'status')
        }),
        ('Usage', {
            'fields': ('credits_used', 'credits_remaining', 'pdfs_uploaded', 'pdfs_remaining')
        }),
        ('Billing Period', {
            'fields': ('current_period_start', 'current_period_end')
        }),
        ('Stripe (Future)', {
            'fields': ('stripe_customer_id', 'stripe_subscription_id'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'cancelled_at'),
            'classes': ('collapse',)
        }),
    )

    def credits_remaining(self, obj):
        return obj.credits_remaining
    credits_remaining.short_description = 'Credits Left'

    def pdfs_remaining(self, obj):
        return obj.pdfs_remaining
    pdfs_remaining.short_description = 'PDFs Left'


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction_type', 'amount', 'balance_after', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__email', 'description']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['user']
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('user', 'transaction_type')
        }),
        ('Transaction', {
            'fields': ('amount', 'balance_after', 'description')
        }),
        ('Metadata', {
            'fields': ('metadata', 'id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
