from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("certificate_generator", "0001_install_plugin"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocReferenceCounter",
            fields=[
                ("name", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
        ),
    ]
