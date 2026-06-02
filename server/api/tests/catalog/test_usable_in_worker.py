from ai_portal.catalog.model import CatalogModel


def test_catalog_model_has_usable_in_worker_default_false():
    col = CatalogModel.__table__.c.usable_in_worker
    assert col is not None
    assert col.default.arg is False
    assert col.nullable is False
