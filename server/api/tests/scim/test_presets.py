"""H2: SCIM Okta + Entra presets — attribute mapper unit tests."""

from __future__ import annotations

from ai_portal.scim.presets import EntraPreset, GenericPreset, OktaPreset, get_preset


def test_get_preset_falls_back_to_generic_for_unknown_name():
    p = get_preset("nonsense")
    assert p.name == "generic"


def test_generic_user_extracts_email_and_external_id():
    payload = {
        "userName": "alice@acme.com",
        "externalId": "ext-1",
        "name": {"givenName": "Alice", "familyName": "Liddell"},
        "emails": [
            {"value": "alice@acme.com", "primary": True},
            {"value": "alt@acme.com"},
        ],
        "active": True,
        "locale": "en-US",
    }
    m = GenericPreset().map_user(payload)
    assert m.external_id == "ext-1"
    assert m.user_name == "alice@acme.com"
    assert m.email == "alice@acme.com"
    assert m.name == "Alice Liddell"
    assert m.active is True
    assert m.locale == "en-US"


def test_generic_user_defaults_active_when_absent():
    m = GenericPreset().map_user({"userName": "x@y.com", "emails": [{"value": "x@y.com"}]})
    assert m.active is True


def test_generic_user_active_false_passthrough():
    m = GenericPreset().map_user(
        {"userName": "x@y.com", "emails": [{"value": "x@y.com"}], "active": False}
    )
    assert m.active is False


def test_okta_user_lowercases_email_and_username():
    m = OktaPreset().map_user(
        {
            "userName": "Alice@ACME.com",
            "externalId": "okta-1",
            "emails": [{"value": "Alice@ACME.com", "primary": True}],
        }
    )
    assert m.email == "alice@acme.com"
    assert m.user_name == "alice@acme.com"


def test_okta_group_extracts_members_with_display_as_email():
    g = OktaPreset().map_group(
        {
            "displayName": "Engineering",
            "externalId": "00g-eng",
            "members": [
                {"value": "00u-1", "display": "Alice@Acme.com"},
                {"value": "00u-2", "display": "Bob@Acme.com"},
                {"value": ""},  # ignored
            ],
        }
    )
    assert g.display_name == "Engineering"
    assert g.external_id == "00g-eng"
    assert [m.external_user_id for m in g.members] == ["00u-1", "00u-2"]
    assert g.members[0].email == "alice@acme.com"


def test_entra_user_falls_back_to_object_id_when_external_id_missing():
    # Entra often sends ``id`` (the objectId) on PUT/PATCH but no externalId.
    payload = {
        "id": "obj-1234",
        "userName": "alice@acme.com",
        "displayName": "Alice Liddell",
        "emails": [{"value": "alice@acme.com", "primary": True}],
    }
    m = EntraPreset().map_user(payload)
    assert m.external_id == "obj-1234"
    # displayName surfaces as the name when ``name`` is missing.
    assert m.name == "Alice Liddell"


def test_entra_user_prefers_external_id_when_present():
    m = EntraPreset().map_user(
        {
            "id": "obj-1234",
            "externalId": "preferred-id",
            "userName": "a@b.com",
            "emails": [{"value": "a@b.com"}],
        }
    )
    assert m.external_id == "preferred-id"


def test_entra_user_uses_enterprise_employee_number_as_fallback():
    payload = {
        "userName": "a@b.com",
        "emails": [{"value": "a@b.com"}],
        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
            "employeeNumber": "E-42"
        },
    }
    m = EntraPreset().map_user(payload)
    assert m.external_id == "E-42"


def test_entra_group_member_external_ids_are_object_ids():
    g = EntraPreset().map_group(
        {
            "displayName": "Admins",
            "id": "group-obj-1",
            "members": [
                {"value": "obj-a", "display": "alice@acme.com"},
                {"value": "obj-b"},
            ],
        }
    )
    assert g.external_id == "group-obj-1"
    assert [m.external_user_id for m in g.members] == ["obj-a", "obj-b"]
