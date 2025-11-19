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
    user_knowledge_base = models.ForeignKey(
        UserKnowledgeBase,
        on_delete=models.CASCADE,
        related_name='uploaded_pdfs'
    )
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, null=True, blank=True)  # Path to saved PDF file
    file_size = models.BigIntegerField()  # in bytes
    chunks_count = models.IntegerField(default=0)
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