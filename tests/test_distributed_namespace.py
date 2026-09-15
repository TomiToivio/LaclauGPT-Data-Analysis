from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.distributed import ProjectNamespace


def test_ep24_namespace_is_collision_safe() -> None:
    ns = ProjectNamespace("ep24")
    assert ns.redis_base == "laclaugpt:ep24"
    assert ns.settings_key("analysis") == "laclaugpt:ep24:settings:analysis:current"
    assert ns.codebook_key("entities", "v2") == "laclaugpt:ep24:codebook:entities:v2"
    assert ns.mongo_collection("annotations") == "ep24__annotations"
    assert ns.s3_key("frames", "source", "0001.jpg") == "projects/ep24/frames/source/0001.jpg"


def test_all_named_projects_are_isolated() -> None:
    names = ("ai26", "ep24", "brazil26", "hungary26")
    namespaces = [ProjectNamespace(name) for name in names]
    assert len({item.redis_base for item in namespaces}) == len(names)
    assert len({item.mongo_collection("annotations") for item in namespaces}) == len(names)
    assert len({item.s3_key("analysis") for item in namespaces}) == len(names)


def test_settings_expose_project_namespace() -> None:
    settings = Settings(project_id="hungary26")
    assert settings.distributed_namespace.settings_key("analysis").startswith(
        "laclaugpt:hungary26:"
    )
    assert settings.distributed_namespace.mongo_collection("runs") == "hungary26__runs"


def test_unknown_collection_kind_is_rejected() -> None:
    ns = ProjectNamespace("ai26")
    try:
        ns.mongo_collection("secrets")
    except ValueError as exc:
        assert "collection kind" in str(exc)
    else:
        raise AssertionError("unknown collection kind should be rejected")
