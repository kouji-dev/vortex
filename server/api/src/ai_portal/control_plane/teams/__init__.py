"""Teams sub-domain of the Control Plane.

Org → team → user hierarchy. Teams group org members for team-scoped role
assignment, per-team API-key counting and usage aggregation. API keys stay
owned by individuals (``api_keys.actor_user_id``); team attribution is derived
through ``team_members``.
"""
