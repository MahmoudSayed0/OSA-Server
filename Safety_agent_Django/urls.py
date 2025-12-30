"""
URL configuration for Safety_agent_Django project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_check(request):
    """Basic health check - Django is running"""
    return JsonResponse({"status": "healthy"})

def ready_check(request):
    """Readiness check - actually test embeddings and DB connection"""
    try:
        from chatlog.langgraph_agent import EMBEDDINGS, get_foundation_vectorstore

        # Test embeddings can actually generate vectors (not just import)
        test_vector = EMBEDDINGS.embed_query("readiness test")
        if not test_vector or len(test_vector) == 0:
            raise Exception("Embeddings returned empty vector")

        # Test vector store connection works
        foundation_vs = get_foundation_vectorstore()

        return JsonResponse({
            "status": "ready",
            "models_loaded": True,
            "embedding_dims": len(test_vector)
        })
    except Exception as e:
        return JsonResponse(
            {"status": "not_ready", "error": str(e)},
            status=503  # Service Unavailable
        )

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),  # Authentication endpoints
    path('api/subscription/', include('subscriptions.urls')),  # Subscription endpoints
    path("chatlog/", include("chatlog.urls")),
    # Health checks
    path('health/', health_check, name='health_check'),
    path('ready/', ready_check, name='ready_check'),
]
