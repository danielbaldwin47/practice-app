# ADR 0004: Cloudflare Tunnel for remote access; API-issued JWTs for auth

## Status

Accepted (2026-07-23)

## Context

Remote access off the home LAN is in scope for 2–3 fully private users. Research recommended Tailscale (zero public exposure), but the household standard is **cloudflared** routing services through an owned domain — no VPN client on devices. Public exposure means app-level auth is the sole gate. Cloudflare Access was considered and rejected: its browser-redirect login is a poor fit for native Flutter clients, and service tokens are clunky for family users.

## Decision

- **Remote access via Cloudflare Tunnel** (`cloudflared` in the Compose stack), exposing the API and PowerSync endpoints on the owned domain. No ports opened; origin stays hidden; TLS and DDoS shielding from Cloudflare.
- **Auth: the TS API issues JWTs itself** — username + strong password per user stored in Postgres, RS256 signing, a JWKS endpoint that `powersync-service` validates against, rate-limited login, and a long-lived per-device refresh token so family members log in once per device.
- No IdP container (Authelia/Keycloak rejected as oversized for 3 users).

## Consequences

- Endpoints are publicly reachable: login hardening (rate limits, strong passwords, short access-token TTL) is a requirement, not a nicety.
- Cloudflare's free proxy caps request bodies (~100 MB): audio upload must use chunked/multipart uploads sized under the cap.
- If exposure posture ever feels wrong, Tailscale remains a drop-in retreat without touching app auth.
