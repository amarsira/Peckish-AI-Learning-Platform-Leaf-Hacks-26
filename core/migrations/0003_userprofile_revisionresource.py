import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0002_session_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "sen_profile",
                    models.CharField(
                        choices=[
                            ("none", "No SEN / default"),
                            ("dyslexia", "Dyslexia"),
                            ("autism", "Autism"),
                            ("adhd", "ADHD"),
                            ("dyscalculia", "Dyscalculia"),
                            ("dyspraxia", "Dyspraxia / DCD"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                ("setup_complete", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="learning_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="RevisionResource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "resource_type",
                    models.CharField(
                        choices=[
                            ("flashcards", "Flashcards"),
                            ("mindmap", "Mind map"),
                            ("flowchart", "Flow chart"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "sen_profile",
                    models.CharField(
                        choices=[
                            ("none", "No SEN / default"),
                            ("dyslexia", "Dyslexia"),
                            ("autism", "Autism"),
                            ("adhd", "ADHD"),
                            ("dyscalculia", "Dyscalculia"),
                            ("dyspraxia", "Dyspraxia / DCD"),
                        ],
                        max_length=20,
                    ),
                ),
                ("content", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revision_resources",
                        to="core.session",
                    ),
                ),
            ],
            options={"ordering": ["resource_type", "-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="revisionresource",
            constraint=models.UniqueConstraint(
                fields=("session", "resource_type", "sen_profile"),
                name="unique_revision_resource_per_sen_session",
            ),
        ),
    ]
