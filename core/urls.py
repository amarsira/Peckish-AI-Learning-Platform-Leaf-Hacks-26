from django.urls import path

from . import views


app_name = "core"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("accounts/google/login/", views.google_login, name="google_login"),
    path("accounts/google/callback/", views.google_callback, name="google_callback"),
    path("logout/", views.logout_user, name="logout"),
    path("profile/setup/", views.profile_setup, name="profile_setup"),
    path("profile/", views.profile, name="profile"),
    path("", views.home, name="home"),
    path("voice/transcribe/", views.transcribe_audio, name="transcribe_audio"),
    path("sessions/<int:session_id>/", views.read_session, name="read"),
    path("sessions/<int:session_id>/organise/<str:resource_type>/", views.revision_resource, name="revision_resource"),
    path("sessions/<int:session_id>/teach/<int:concept_id>/", views.teach_concept, name="teach"),
    path("sessions/<int:session_id>/summary/", views.session_summary, name="summary"),
    path("fossils/<int:fossil_id>/reteach/", views.reteach_fossil, name="reteach"),
]
