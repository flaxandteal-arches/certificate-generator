# Arches Certificate Generator Plugin

A plugin for [Arches](https://www.archesproject.org/) 8.x that generates certificate documents from registered resource data using configurable `.docx` templates.

---

## Requirements

- Arches 8.x
- Python 3.10+
- Docker (if using the standard Arches containerised setup)

---

## Installation

Add the plugin as a dependency in your host Arches project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "arches>=8.0",
    "arches-certificate-generator @ git+https://github.com/flaxandteal-arches/certificate-generator.git",
]
```

Then reinstall your project dependencies:

```bash
pip install -e .
```
or rebuild your project in the way you usually rebuild after adding a dependency.

---

## Configuration

### 1. Add to `INSTALLED_APPS`

In your host project's `settings.py`:

```python
INSTALLED_APPS = [
    ...
    "certificate_generator",
]
```

### 2. Register the URLs

In your host project's `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    ...
    path("", include("certificate_generator.urls")),
]
```

This exposes the following endpoints:

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/plugins/certificate-generator/` | Plugin view |
| GET | `/certificate-generator/resources/` | Fetch available resources |
| GET | `/certificate-generator/templates` | Fetch available templates |
| POST | `/certificate-generator/process-template/` | Process the selected parameters into certificate |

### 3. Register the plugin with Arches

Run the following management command once after installation:

```bash
python manage.py plugin register --source certificate_generator/plugins/certificate-generator-plugin.json
```

Or if running inside Docker:

```bash
docker exec -it <container_name> python manage.py plugin register \
  --source certificate_generator/plugins/certificate-generator-plugin.json
```

The plugin will then appear in the Arches sidebar navigation.

### Document reference numbers (optional)

Certified Copy of Entry documents get a sequential `docReference` (e.g. `CC0448`),
issued from a database counter and bumped on every generation. Settings:

```python
CERTIFICATE_GENERATOR_DOC_REF_PREFIX = "CC"  # default
CERTIFICATE_GENERATOR_DOC_REF_START = 448    # first number to issue, default 1
CERTIFICATE_GENERATOR_DOC_REF_WIDTH = 4      # zero padding, default 4
```

The number issued is `max(last issued + 1, START)`: raising START moves the sequence
forward, lowering it never reissues a number. Run `migrate` after upgrading.
