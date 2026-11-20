"""Sequential document references (e.g. CC0448) for generated certificates."""

from django.conf import settings
from django.db import transaction

from certificate_generator.models import DocReferenceCounter, DocReferenceRecord

DEFAULT_PREFIX = "CC"
DEFAULT_START = 1
DEFAULT_WIDTH = 4


def next_doc_reference(counter_name: str = "certified-copy-of-entry", user=None, **meta) -> str:
    """Issue the next reference, bumping the stored counter atomically.

    Settings (all optional):
      CERTIFICATE_GENERATOR_DOC_REF_PREFIX  default "CC"
      CERTIFICATE_GENERATOR_DOC_REF_START   first number to issue, default 1
      CERTIFICATE_GENERATOR_DOC_REF_WIDTH   zero padding, default 4

    The number issued is max(last issued + 1, START), so raising START later
    moves the sequence forward, while lowering it never reissues a number.

    Every issued reference is also logged as a DocReferenceRecord (in the same
    transaction) with the generating user and any extra fields in ``meta``
    (resource_id, resource_version_id, resource_name, template_version).
    """
    prefix = getattr(settings, "CERTIFICATE_GENERATOR_DOC_REF_PREFIX", DEFAULT_PREFIX)
    start = int(getattr(settings, "CERTIFICATE_GENERATOR_DOC_REF_START", DEFAULT_START))
    width = int(getattr(settings, "CERTIFICATE_GENERATOR_DOC_REF_WIDTH", DEFAULT_WIDTH))

    with transaction.atomic():
        counter, _ = DocReferenceCounter.objects.select_for_update().get_or_create(
            name=counter_name
        )
        number = max(counter.last_number + 1, start)
        counter.last_number = number
        counter.save(update_fields=["last_number"])

        reference = f"{prefix}{number:0{width}d}"
        authenticated = user is not None and getattr(user, "is_authenticated", False)
        DocReferenceRecord.objects.create(
            reference=reference,
            number=number,
            counter_name=counter_name,
            generated_by=user if authenticated else None,
            generated_by_username=user.get_username() if authenticated else "",
            **meta,
        )

    return reference
