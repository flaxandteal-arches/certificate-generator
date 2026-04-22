from django.urls import path
from certificate_generator.views import (
    certificate_generator_plugin_view,
    certificate_generator_plugin_get_resources,
    certificate_generator_plugin_process_template,
)

urlpatterns = [
    path(
        "certificate-generator/templates/",
        certificate_generator_plugin_view.CertificateGeneratorPluginView.as_view(),
        name="certificate-generator",
    ),
    path(
        "certificate-generator/get-resources/",
        certificate_generator_plugin_get_resources.CertificateGeneratorPluginGetResources.as_view(),
        name="certificate-generator-get-resources",
    ),
    path(
        "certificate-generator/process-template/",
        certificate_generator_plugin_process_template.CertificateGeneratorPluginProcessTemplate.as_view(),
        name="certificate-generator-process-template",
    ),
]