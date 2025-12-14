from django.db import models
from django.contrib.auth.models import User
import uuid


class UserKnowledgeBase(models.Model):
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    collection_name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.username


class ConversationLog(models.Model):
    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="conversations",
        null=True,
        blank=True
    )
    user_input = models.TextField()                     # stores user input
    response = models.TextField()                       # stores system/AI response
    created_at = models.DateTimeField(auto_now_add=True) # auto timestamp when created
    is_succeeded = models.BooleanField(default=False)    # true/false status

    def __str__(self):
        return f"Input: {self.user_input[:30]}... | Success: {self.is_succeeded}"


class UploadedPDF(models.Model):
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='uploaded_pdfs'
    )
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, null=True, blank=True)  # Path to saved PDF file
    file_size = models.BigIntegerField()  # in bytes
    chunks_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploading')
    error_message = models.TextField(null=True, blank=True)  # Store error if failed
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} ({self.user_knowledge_base.username})"


class ChatSession(models.Model):
    session_id = models.CharField(max_length=255, unique=True, default=uuid.uuid4, db_index=True)
    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )
    title = models.CharField(max_length=500, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user_knowledge_base', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.user_knowledge_base.username}"

    def save(self, *args, **kwargs):
        # Auto-generate title from first message if still "New Chat"
        if self.title == "New Chat" and self.pk:
            first_user_msg = self.messages.filter(role='user').first()
            if first_user_msg:
                # Take first 50 chars of first message
                self.title = first_user_msg.content[:50]
                if len(first_user_msg.content) > 50:
                    self.title += "..."
        super().save(*args, **kwargs)


class ChatMessage(models.Model):
    message_id = models.CharField(max_length=255, unique=True, default=uuid.uuid4, db_index=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=50)  # 'user' or 'assistant'
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:30]}..."


class DocumentSummary(models.Model):
    """Stores AI-generated summaries of user's documents (NotebookLM-style)"""
    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='document_summaries'
    )
    title = models.CharField(max_length=500)  # Generated title
    emoji = models.CharField(max_length=10, default='📄')  # Topic-relevant emoji
    summary = models.TextField()  # Main summary text
    key_topics = models.JSONField(default=list)  # Highlighted key terms
    suggested_questions = models.JSONField(default=list)  # AI-generated questions
    source_count = models.IntegerField(default=0)  # Number of documents
    source_filenames = models.JSONField(default=list)  # List of source filenames
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.emoji} {self.title} ({self.user_knowledge_base.username})"


class UserFeedback(models.Model):
    """Stores user feedback on AI responses and summaries"""
    FEEDBACK_TYPES = [
        ('thumbs_up', 'Thumbs Up'),
        ('thumbs_down', 'Thumbs Down'),
        ('save_note', 'Saved to Notes'),
        ('copy', 'Copied'),
    ]

    CONTENT_TYPES = [
        ('summary', 'Document Summary'),
        ('chat_response', 'Chat Response'),
    ]

    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='feedback'
    )
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPES)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    content_id = models.CharField(max_length=255, blank=True, null=True)  # Reference to summary or message
    content_preview = models.TextField(blank=True, null=True)  # Preview of the content
    comment = models.TextField(blank=True, null=True)  # Optional user comment
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.feedback_type} on {self.content_type} ({self.user_knowledge_base.username})"


class SavedNote(models.Model):
    """User's saved notes from summaries and responses"""
    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='saved_notes'
    )
    title = models.CharField(max_length=500)
    content = models.TextField()
    source_type = models.CharField(max_length=50)  # 'summary' or 'chat_response'
    source_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title[:50]} ({self.user_knowledge_base.username})"


class FoundationDocument(models.Model):
    """
    Foundation Knowledge Base - Authoritative mining safety regulations.
    This is a SHARED collection accessible by all users (read-only).
    Contains MSHA, OSHA, state regulations, and best practices.
    """
    CATEGORY_CHOICES = [
        ('msha', 'MSHA Regulations'),
        ('osha', 'OSHA Standards'),
        ('state', 'State Regulations'),
        ('best_practice', 'Best Practices'),
        ('training', 'Training Materials'),
    ]

    title = models.CharField(max_length=500)
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    source_url = models.URLField(blank=True, null=True)  # For automated fetching
    regulation_code = models.CharField(max_length=100, blank=True)  # e.g., "30 CFR 56"
    description = models.TextField(blank=True)  # Brief description of the document
    effective_date = models.DateField(null=True, blank=True)
    file_size = models.BigIntegerField(default=0)  # in bytes
    chunks_count = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ('uploading', 'Uploading'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='uploading'
    )
    error_message = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The collection name for Foundation KB (shared by all users)
    FOUNDATION_COLLECTION = 'foundation_mining_kb'

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Foundation Document'
        verbose_name_plural = 'Foundation Documents'

    def __str__(self):
        return f"[{self.category.upper()}] {self.title}"