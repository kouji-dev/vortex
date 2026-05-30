"""Social login — consumer OAuth (Google / GitHub / GitLab).

Distinct from enterprise SSO (``auth/idp``): social login is a self-service
consumer sign-in that any deployment may enable, independent of an org's IdP.

Provider pattern mirrors ``auth/idp``: ``protocol.py`` + ``providers/`` +
``registry.py``. Routes call :meth:`SocialProvider.authorize_url` to start and
:meth:`SocialProvider.exchange` to finish, receiving :class:`UserClaims`.
"""
