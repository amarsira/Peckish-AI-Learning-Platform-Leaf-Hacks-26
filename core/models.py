from django.conf import settings
from django.db import models


class Session(models.Model):
    SOURCE_UPLOAD = "upload"
    SOURCE_GENERATED = "generated"

    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, "Uploaded PDF"),
        (SOURCE_GENERATED, "Gemini generated"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_sessions",
        null=True,
        blank=True,
    )
    topic_title = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    raw_notes = models.TextField(blank=True)
    pet_level = models.PositiveIntegerField(default=1)
    pet_xp = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.topic_title


class UserProfile(models.Model):
    SEN_NONE = "none"
    SEN_DYSLEXIA = "dyslexia"
    SEN_AUTISM = "autism"
    SEN_ADHD = "adhd"
    SEN_DYSCALCULIA = "dyscalculia"
    SEN_DYSPRAXIA = "dyspraxia"

    SEN_CHOICES = [
        (SEN_NONE, "No SEN / default"),
        (SEN_DYSLEXIA, "Dyslexia"),
        (SEN_AUTISM, "Autism"),
        (SEN_ADHD, "ADHD"),
        (SEN_DYSCALCULIA, "Dyscalculia"),
        (SEN_DYSPRAXIA, "Dyspraxia / DCD"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_profile",
    )
    sen_profile = models.CharField(max_length=20, choices=SEN_CHOICES, default=SEN_NONE)
    setup_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user} - {self.get_sen_profile_display()}"


class Concept(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="concepts",
    )
    title = models.CharField(max_length=255)
    source_notes = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.title


class TeachingTurn(models.Model):
    SATISFIED = "SATISFIED"
    CURIOUS = "CURIOUS"
    CONFUSED = "CONFUSED"

    REACTION_CHOICES = [
        (SATISFIED, "Satisfied"),
        (CURIOUS, "Curious"),
        (CONFUSED, "Confused"),
    ]

    concept = models.ForeignKey(
        Concept,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    turn_number = models.PositiveIntegerField()
    student_text = models.TextField()
    reaction_type = models.CharField(max_length=20, choices=REACTION_CHOICES)
    peckish_response = models.TextField()
    feedback_summary = models.TextField(blank=True)
    subtle_hint = models.TextField(blank=True)
    follow_up_question = models.TextField(blank=True)
    missing_points = models.JSONField(default=list, blank=True)
    correct_points = models.JSONField(default=list, blank=True)
    depth_score = models.PositiveIntegerField()
    xp_awarded = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["turn_number", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["concept", "turn_number"],
                name="unique_turn_number_per_concept",
            )
        ]

    def __str__(self) -> str:
        return f"{self.concept.title} turn {self.turn_number}"


class Fossil(models.Model):
    concept = models.ForeignKey(
        Concept,
        on_delete=models.CASCADE,
        related_name="fossils",
    )
    fossil_name = models.CharField(max_length=100)
    what_they_said = models.TextField()
    the_truth = models.TextField()
    flavor_text = models.TextField()
    source_notes_snapshot = models.TextField(blank=True)
    student_attempts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    re_taught_successfully = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.fossil_name


class RevisionResource(models.Model):
    FLASHCARDS = "flashcards"
    MINDMAP = "mindmap"
    FLOWCHART = "flowchart"

    RESOURCE_CHOICES = [
        (FLASHCARDS, "Flashcards"),
        (MINDMAP, "Mind map"),
        (FLOWCHART, "Flow chart"),
    ]

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="revision_resources",
    )
    resource_type = models.CharField(max_length=20, choices=RESOURCE_CHOICES)
    sen_profile = models.CharField(max_length=20, choices=UserProfile.SEN_CHOICES)
    content = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["resource_type", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "resource_type", "sen_profile"],
                name="unique_revision_resource_per_sen_session",
            )
        ]

    def __str__(self) -> str:
        return f"{self.session.topic_title} {self.resource_type}"
