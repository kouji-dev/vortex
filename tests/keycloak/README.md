# Keycloak test IdP (enterprise SSO E2E)

Local OIDC identity provider for the enterprise SSO flow. Used by the
selfhosted auth mode E2E (`apps/frontend/e2e/auth/enterprise-sso.spec.ts`).

## Run

```bash
docker compose -f tests/keycloak/docker-compose.yml up -d
# wait for health, then:
curl http://localhost:8080/realms/acme-corp/.well-known/openid-configuration
docker compose -f tests/keycloak/docker-compose.yml down
```

- Keycloak 26, `start-dev --import-realm`, in-memory store (no DB, no persistence).
- Admin console: <http://localhost:8080> — `admin` / `admin`.
- Realms imported from `./realms/*.json` on first boot.

## Realm: `acme-corp` (the must-have — customer IdP)

| Thing | Value |
|---|---|
| Realm | `acme-corp` |
| Issuer | `http://localhost:8080/realms/acme-corp` |
| Client ID | `vortex-app` |
| Client secret | `acme-enterprise-secret` |
| Signing alg | RS256 (JWKS at issuer `/protocol/openid-connect/certs`) |
| Groups claim | `groups` (group names, `full.path=false`) |
| Group → role | `IT-Admins` → admin, `Engineering` → member |

Users (password `Passw0rd!`):

| User | Group | Expected app role |
|---|---|---|
| `alice@acme.test` | `IT-Admins` | admin |
| `bob@acme.test` | `Engineering` | member |

### Verify the `groups` claim (Direct Access Grant)

```bash
curl -s -X POST \
  http://localhost:8080/realms/acme-corp/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=vortex-app \
  -d client_secret=acme-enterprise-secret \
  -d username=alice@acme.test \
  -d password='Passw0rd!' \
  -d scope=openid | jq -r '.id_token' | cut -d. -f2 | base64 -d 2>/dev/null
# id_token payload should contain "groups": ["IT-Admins"]
```

## Realm: `vortex-saas` (optional — SaaS-as-our-IdP)

Minimal second realm (client `vortex-app`, secret `vortex-saas-secret`,
user `owner@vortex.test` / `Passw0rd!`). Not required by the default suite.

## Backend env to point the app at this IdP (selfhosted mode)

The enterprise SSO spec is **skipped unless `E2E_KEYCLOAK=1`** is set, because
it needs the backend reconfigured for OIDC. Required backend env:

```bash
DEPLOYMENT_MODE=selfhosted
OIDC_ISSUER=http://localhost:8080/realms/acme-corp
OIDC_CLIENT_ID=vortex-app
OIDC_CLIENT_SECRET=acme-enterprise-secret
OIDC_GROUPS_CLAIM=groups
# group -> role mapping consumed by map_groups_to_role:
OIDC_ADMIN_GROUPS=IT-Admins
```

And for Playwright:

```bash
E2E_KEYCLOAK=1   # un-skips enterprise-sso.spec.ts
```

> The exact backend env var names must match `server/api`'s OIDC config loader.
> Confirm against the live config before the final test pass — this README lists
> the documented flow, not a verified wiring.
