from django.db import migrations

# Snapshot of plugins/certificate-generator-plugin.json at migration time.
# Kept inline (not read from the file) so the migration stays a fixed point in
# history even if the json changes later.
PLUGIN_ID = "7517ca99-689d-4840-acdf-bc65a449c30a"
PLUGIN = {
    "name": "Certificate Generator",
    "icon": "fa fa-file",
    "component": "views/components/plugins/certificate-generator-plugin",
    "componentname": "certificate-generator-plugin",
    "config": {"show": True},
    "slug": "certificate-generator-plugin",
    "sortorder": 0,
}


def install_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin.objects.get_or_create(pluginid=PLUGIN_ID, defaults=PLUGIN)


def remove_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin.objects.filter(pluginid=PLUGIN_ID).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("models", "6979_manifest_manager"),
    ]

    operations = [
        migrations.RunPython(install_plugin, remove_plugin),
    ]
