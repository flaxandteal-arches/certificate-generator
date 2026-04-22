from django.apps import AppConfig


class CertificateGeneratorConfig(AppConfig):
    name = "certificate_generator"
    verbose_name = "Certificate Generator"

    def ready(self):
        pass