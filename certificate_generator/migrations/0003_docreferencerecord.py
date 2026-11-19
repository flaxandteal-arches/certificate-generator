import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("certificate_generator", "0002_docreferencecounter"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocReferenceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(max_length=50, unique=True)),
                ("number", models.PositiveIntegerField()),
                ("counter_name", models.CharField(db_index=True, max_length=100)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("generated_by_username", models.CharField(blank=True, default="", max_length=150)),
                ("resource_id", models.CharField(blank=True, default="", max_length=64)),
                ("resource_version_id", models.CharField(blank=True, default="", max_length=64)),
                ("resource_name", models.CharField(blank=True, default="", max_length=500)),
                ("template_version", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-generated_at"]},
        ),
    ]
