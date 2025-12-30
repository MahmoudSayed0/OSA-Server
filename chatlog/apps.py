from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ChatlogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chatlog'

    def ready(self):
        """Warm up embeddings and vector store on startup to prevent cold start errors."""
        import os
        # Only run in main process (not in migrations or shell)
        if os.environ.get('RUN_MAIN') == 'true' or os.environ.get('DJANGO_SETTINGS_MODULE'):
            try:
                logger.info("[STARTUP] Warming up HuggingFace embeddings...")
                from .langgraph_agent import EMBEDDINGS

                # Force embedding model to fully load by doing a test embedding
                test_embedding = EMBEDDINGS.embed_query("warmup test query")
                logger.info(f"[STARTUP] Embeddings ready: {len(test_embedding)} dimensions")

                # Test vector store connection
                logger.info("[STARTUP] Testing vector store connection...")
                from .langgraph_agent import get_foundation_vectorstore
                foundation_vs = get_foundation_vectorstore()
                logger.info("[STARTUP] Vector store connection ready")

                logger.info("[STARTUP] All ML models and connections warmed up successfully!")
            except Exception as e:
                logger.error(f"[STARTUP] Warmup failed (non-fatal): {e}")
