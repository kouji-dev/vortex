from ai_portal.auth.oidc.role_map import map_groups_to_role
MAP = {"IT-Admins": "admin", "Owners": "owner", "Engineering": "member"}

def test_maps_matched_group():
    assert map_groups_to_role(["Engineering"], MAP) == "member"

def test_unmatched_fall_back_to_default():
    assert map_groups_to_role(["Finance"], MAP, default="viewer") == "viewer"
    assert map_groups_to_role([], MAP) == "member"

def test_highest_priority_wins():
    assert map_groups_to_role(["Engineering", "Owners"], MAP) == "owner"

def test_unknown_target_role_ignored():
    assert map_groups_to_role(["X"], {"X": "sysadmin"}, default="member") == "member"
