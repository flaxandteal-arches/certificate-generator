from django.conf import settings
from django.db import models


class DocReferenceCounter(models.Model):
    """Last document reference number issued, one row per counter name."""

    name = models.CharField(max_length=100, primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "certificate_generator"


class DocReferenceRecord(models.Model):
    """One row per issued document reference, so it can be traced back later."""

    reference = models.CharField(max_length=50, unique=True)
    number = models.PositiveIntegerField()
    counter_name = models.CharField(max_length=100, db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Snapshot so the record still names the person if the account is deleted.
    generated_by_username = models.CharField(max_length=150, blank=True, default="")
    resource_id = models.CharField(max_length=64, blank=True, default="")
    resource_version_id = models.CharField(max_length=64, blank=True, default="")
    resource_name = models.CharField(max_length=500, blank=True, default="")
    template_version = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        app_label = "certificate_generator"
        ordering = ["-generated_at"]
