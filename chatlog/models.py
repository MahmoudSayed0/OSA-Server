from django.db import models
from django.contrib.auth.models import User


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