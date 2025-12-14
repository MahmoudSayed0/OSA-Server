from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    """
    Extended User model with additional fields for OAuth and knowledge base.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    # OAuth related fields
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    avatar_url = models.URLField(max_length=500, null=True, blank=True)

    # Knowledge base collection (migrated from UserKnowledgeBase)
    collection_name = models.CharField(max_length=255, unique=True, null=True, blank=True)

    # Profile fields
    full_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Legacy migration tracking
    migrated_from_legacy = models.BooleanField(default=False)
    legacy_user_kb_id = models.IntegerField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'accounts_user'

    def save(self, *args, **kwargs):
        # Auto-generate collection name if not set
        if not self.collection_name and self.username:
            base_name = self.username.lower().replace(' ', '_').replace('@', '_').replace('.', '_')
            self.collection_name = f"pdf_chunks_{base_name}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
