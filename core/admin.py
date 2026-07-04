from django.contrib import admin

from .models import Concept, Fossil, RevisionResource, Session, TeachingTurn, UserProfile


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("topic_title", "user", "source_type", "pet_level", "pet_xp", "created_at")
    list_filter = ("source_type", "user")
    search_fields = ("topic_title", "raw_notes", "user__email", "user__username")


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("title", "session", "order")
    list_filter = ("session",)
    search_fields = ("title", "source_notes")


@admin.register(TeachingTurn)
class TeachingTurnAdmin(admin.ModelAdmin):
    list_display = ("concept", "turn_number", "reaction_type", "depth_score", "xp_awarded", "created_at")
    list_filter = ("reaction_type",)
    search_fields = ("student_text", "peckish_response", "feedback_summary", "subtle_hint")


@admin.register(Fossil)
class FossilAdmin(admin.ModelAdmin):
    list_display = ("fossil_name", "concept", "re_taught_successfully", "created_at")
    list_filter = ("re_taught_successfully",)
    search_fields = ("fossil_name", "what_they_said", "the_truth", "source_notes_snapshot")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "sen_profile", "setup_complete", "updated_at")
    list_filter = ("sen_profile", "setup_complete")
    search_fields = ("user__email", "user__username", "user__first_name")


@admin.register(RevisionResource)
class RevisionResourceAdmin(admin.ModelAdmin):
    list_display = ("session", "resource_type", "sen_profile", "updated_at")
    list_filter = ("resource_type", "sen_profile")
    search_fields = ("session__topic_title",)
