"""ResourceMapper image visibility and lot-on-plan rules. Run: python3 test_resource_mapper.py"""

import sys
import types

# Stubbed so the module imports without a Django settings module; the code under
# test only reaches settings through the IIIF helpers, which are patched out.
_conf = types.ModuleType("django.conf")
_conf.settings = type("S", (), {"PUBLIC_SERVER_ADDRESS": "https://example.test"})()
_django = types.ModuleType("django")
_django.conf = _conf
sys.modules.setdefault("django", _django)
sys.modules.setdefault("django.conf", _conf)

from certificate_generator.views.mappers.resource_mapper import ResourceMapper


def mapper():
    m = ResourceMapper.__new__(ResourceMapper)
    m._attach_iiif_images = lambda *a, **k: None
    m._crop_hero = lambda *a, **k: None
    return m


def site_plans(*visibilities):
    images = [
        {"_": [{"path": f"uploadedfiles/{n}.jpg"}], "visibility": list(v)}
        for n, v in enumerate(visibilities)
    ]
    resource = {"images": images}
    mapper()._map_images(resource)
    return [e["filename"] for e in resource["site_plan"]]


def test_available_alone_is_enough():
    assert site_plans(["Available", "Site Plan"]) == ["0.jpg"]


def test_unavailable_images_are_dropped():
    assert site_plans(["Public", "Site Plan"]) == []


def test_lot_on_plan_entries_are_line_separated_per_column():
    lots = [{"lot": str(n), "plan": f"RP{n}00"} for n in range(1, 5)]
    resource = {"location_data": {"lot_on_plan": lots}}
    mapper()._map_lot_on_plan(resource)
    assert resource["mapped_lot_on_plan"] == {
        "column_1": ["1 RP100", "\n2 RP200"],
        "column_2": ["3 RP300", "\n4 RP400"],
        "column_3": [],
    }


if __name__ == "__main__":
    for name, case in sorted(globals().items()):
        if name.startswith("test_"):
            case()
            print(f"ok  {name}")
    print("\nall passed")
