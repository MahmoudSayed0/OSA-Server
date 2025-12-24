from django.urls import path
from .views import (
    upload_pdf, ask_agent, get_chat_history, clear_chat_history,
    create_user, delete_user, get_all_users, list_pdfs, delete_pdf, get_pdf_file, get_pdf_status,
    create_session, list_sessions, get_session_messages, update_session, delete_session,
    get_document_summary, submit_feedback, get_feedback_stats,
    # Foundation KB Admin
    upload_foundation_pdf, list_foundation_documents, delete_foundation_document,
    get_foundation_document_status, get_foundation_stats,
    # Database Stats & RAG Evaluation
    get_db_stats, run_rag_evaluation
)
from .admin_views import (
    # Authentication
    admin_login, admin_me,
    # Dashboard Analytics
    dashboard_stats, user_growth_data, document_upload_data, recent_activity,
    # Advanced Analytics
    revenue_trends, user_activity_metrics, subscription_distribution, system_health_metrics,
    # User Management
    list_users, get_user_detail, update_user_subscription, adjust_user_credits, delete_user as delete_user_admin,
    # User Detail Views
    user_activity_history, user_usage_analytics, user_billing_info, user_documents_list,
    # Document Management
    list_all_documents, delete_document,
    # Subscription Plan Management
    list_subscription_plans, get_subscription_plan, create_subscription_plan,
    update_subscription_plan, delete_subscription_plan,
)

urlpatterns = [
    # User Management
    path("create-user/", create_user, name="create_user"),
    path("delete-user/", delete_user, name="delete_user"),
    path("get-all-users/", get_all_users, name="get_all_users"),

    # PDF Management
    path("upload-pdf/", upload_pdf, name="upload_pdf"),
    path("list-pdfs/", list_pdfs, name="list_pdfs"),
    path("delete-pdf/", delete_pdf, name="delete_pdf"),
    path("get-pdf/<int:pdf_id>/", get_pdf_file, name="get_pdf_file"),
    path("pdf-status/<int:pdf_id>/", get_pdf_status, name="get_pdf_status"),

    # Chat Agent
    path("ask-agent/", ask_agent, name="ask_agent"),

    # Legacy Chat History (backward compatibility)
    path("chat-history/", get_chat_history, name="get_chat_history"),
    path("clear-chat-history/", clear_chat_history, name="clear_chat_history"),

    # Session Management
    path("sessions/", create_session, name="create_session"),
    path("sessions/list/", list_sessions, name="list_sessions"),
    path("sessions/<str:session_id>/", update_session, name="update_session"),
    path("sessions/<str:session_id>/delete/", delete_session, name="delete_session"),
    path("sessions/<str:session_id>/messages/", get_session_messages, name="get_session_messages"),

    # Document Summary & Feedback (NotebookLM-style)
    path("summary/", get_document_summary, name="get_document_summary"),
    path("feedback/", submit_feedback, name="submit_feedback"),
    path("feedback/stats/", get_feedback_stats, name="get_feedback_stats"),

    # Foundation Knowledge Base (Admin)
    path("admin/foundation/upload/", upload_foundation_pdf, name="upload_foundation_pdf"),
    path("admin/foundation/list/", list_foundation_documents, name="list_foundation_documents"),
    path("admin/foundation/<int:doc_id>/delete/", delete_foundation_document, name="delete_foundation_document"),
    path("admin/foundation/status/<int:doc_id>/", get_foundation_document_status, name="get_foundation_document_status"),

    # Foundation Knowledge Base (Public)
    path("foundation/stats/", get_foundation_stats, name="get_foundation_stats"),

    # ==============================
    # ADMIN PANEL ROUTES (Staff-only)
    # ==============================

    # Admin Authentication
    path("admin/login/", admin_login, name="admin_login"),
    path("admin/me/", admin_me, name="admin_me"),

    # Admin Dashboard Analytics
    path("admin/dashboard/stats/", dashboard_stats, name="dashboard_stats"),
    path("admin/dashboard/user-growth/", user_growth_data, name="user_growth_data"),
    path("admin/dashboard/document-uploads/", document_upload_data, name="document_upload_data"),
    path("admin/dashboard/recent-activity/", recent_activity, name="recent_activity"),

    # Database Statistics (Admin)
    path("admin/db-stats/", get_db_stats, name="get_db_stats"),

    # RAG Evaluation (Admin)
    path("admin/rag-evaluation/", run_rag_evaluation, name="run_rag_evaluation"),

    # Advanced Analytics (Charts)
    path("admin/analytics/revenue-trends/", revenue_trends, name="revenue_trends"),
    path("admin/analytics/user-activity/", user_activity_metrics, name="user_activity_metrics"),
    path("admin/analytics/subscription-distribution/", subscription_distribution, name="subscription_distribution"),
    path("admin/analytics/system-health/", system_health_metrics, name="system_health_metrics"),

    # Admin User Management
    path("admin/users/", list_users, name="list_users"),
    path("admin/users/<uuid:user_id>/", get_user_detail, name="get_user_detail"),
    path("admin/users/<uuid:user_id>/subscription/", update_user_subscription, name="update_user_subscription"),
    path("admin/users/<uuid:user_id>/credits/", adjust_user_credits, name="adjust_user_credits"),
    path("admin/users/<uuid:user_id>/delete/", delete_user_admin, name="delete_user_admin"),

    # User Detail Views
    path("admin/users/<uuid:user_id>/activity/", user_activity_history, name="user_activity_history"),
    path("admin/users/<uuid:user_id>/usage/", user_usage_analytics, name="user_usage_analytics"),
    path("admin/users/<uuid:user_id>/billing/", user_billing_info, name="user_billing_info"),
    path("admin/users/<uuid:user_id>/documents/", user_documents_list, name="user_documents_list"),

    # Admin Document Management
    path("admin/documents/", list_all_documents, name="list_all_documents"),
    path("admin/documents/<int:doc_id>/delete/", delete_document, name="delete_document"),

    # Admin Subscription Plan Management
    path("admin/plans/", list_subscription_plans, name="list_subscription_plans"),
    path("admin/plans/<uuid:plan_id>/", get_subscription_plan, name="get_subscription_plan"),
    path("admin/plans/create/", create_subscription_plan, name="create_subscription_plan"),
    path("admin/plans/<uuid:plan_id>/update/", update_subscription_plan, name="update_subscription_plan"),
    path("admin/plans/<uuid:plan_id>/delete/", delete_subscription_plan, name="delete_subscription_plan"),
]
