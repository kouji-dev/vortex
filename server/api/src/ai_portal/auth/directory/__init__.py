"""Directory authentication — LDAP / Active Directory direct bind.

The user enters their credentials into our login form; the app binds against
the directory to verify them. Service-account bind is used to find the user's
DN, then we re-bind as the user to confirm the password.

Provider pattern mirrors ``auth/idp`` and ``auth/social``: ``protocol.py`` +
``providers/`` + ``registry.py``. ``ldap`` is the generic provider;
``active_directory`` is a preset with AD-friendly defaults.
"""
