# Generated migration for GoToSocial social posting integration

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("storage", "0004_add_sort_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharelink",
            name="posted_to_social",
            field=models.BooleanField(
                default=False,
                help_text="Whether this link was posted to GoToSocial",
            ),
        ),
        migrations.AddField(
            model_name="sharelink",
            name="social_post_id",
            field=models.CharField(
                blank=True,
                help_text="GoToSocial status ID (for deletion/editing)",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sharelink",
            name="social_post_url",
            field=models.URLField(
                blank=True,
                help_text="Public URL of the social post",
                null=True,
            ),
        ),
    ]
