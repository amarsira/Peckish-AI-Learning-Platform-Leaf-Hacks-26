# Generated for the Peckish hackathon app.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Session",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("topic_title", models.CharField(max_length=255)),
                (
                    "source_type",
                    models.CharField(
                        choices=[("upload", "Uploaded PDF"), ("generated", "Gemini generated")],
                        max_length=20,
                    ),
                ),
                ("raw_notes", models.TextField(blank=True)),
                ("pet_level", models.PositiveIntegerField(default=1)),
                ("pet_xp", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Concept",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("source_notes", models.TextField()),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="concepts",
                        to="core.session",
                    ),
                ),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="Fossil",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fossil_name", models.CharField(max_length=100)),
                ("what_they_said", models.TextField()),
                ("the_truth", models.TextField()),
                ("flavor_text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("re_taught_successfully", models.BooleanField(default=False)),
                (
                    "concept",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fossils",
                        to="core.concept",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TeachingTurn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("turn_number", models.PositiveIntegerField()),
                ("student_text", models.TextField()),
                (
                    "reaction_type",
                    models.CharField(
                        choices=[
                            ("SATISFIED", "Satisfied"),
                            ("CURIOUS", "Curious"),
                            ("CONFUSED", "Confused"),
                        ],
                        max_length=20,
                    ),
                ),
                ("peckish_response", models.TextField()),
                ("depth_score", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "concept",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="core.concept",
                    ),
                ),
            ],
            options={"ordering": ["turn_number", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="teachingturn",
            constraint=models.UniqueConstraint(
                fields=("concept", "turn_number"),
                name="unique_turn_number_per_concept",
            ),
        ),
    ]
