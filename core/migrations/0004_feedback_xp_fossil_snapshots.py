from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_userprofile_revisionresource"),
    ]

    operations = [
        migrations.AddField(
            model_name="teachingturn",
            name="feedback_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="teachingturn",
            name="subtle_hint",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="teachingturn",
            name="follow_up_question",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="teachingturn",
            name="missing_points",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="teachingturn",
            name="correct_points",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="teachingturn",
            name="xp_awarded",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fossil",
            name="source_notes_snapshot",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="fossil",
            name="student_attempts",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
