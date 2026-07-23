# ADR 0004: Cloudflare Tunnel for remote access; API-issued JWTs for auth

## Status

Accepted (2026-07-23)

## Context

Remote access off the home LAN is in scope for 2–3 fully private users. Research recommended Tailscale (zero public exposure), but the household standard is **cloudflared** routing services through an owned domain — no VPN client on devices. Public exposure means app-level auth is the sole gate. Cloudflare Access was considered and rejected: its browser-redirect login is a poor fit for native Flutter clients, and service tokens are clunky for family users.

## Decision

- **Remote access via Cloudflare Tunnel** (`cloudflared` in the Compose stack), exposing the API, PowerSync **and MinIO S3** endpoints on the owned domain — three hostnames. No ports opened; origin stays hidden; TLS and DDoS shielding from Cloudflare.
- **Auth: the TS API issues JWTs itself** — username + strong password per user stored in Postgres, RS256 signing, a JWKS endpoint that `powersync-service` validates against, rate-limited login, and a long-lived per-device refresh token so family members log in once per device.
- No IdP container (Authelia/Keycloak rejected as oversized for 3 users).

## Consequences

- Endpoints are publicly reachable: login hardening (rate limits, strong passwords, short access-token TTL) is a requirement, not a nicety.
- Cloudflare's free proxy caps request bodies (~100 MB): audio upload must use chunked/multipart uploads sized under the cap. This lands on the MinIO hostname, since devices upload there directly.
- MinIO's S3 port is exposed but its **console** port is not.
- If exposure posture ever feels wrong, Tailscale remains a drop-in retreat without touching app auth.

## Amendments

- **2026-07-23**, from the [stack spike](https://github.com/danielbaldwin47/practice-app/issues/19): MinIO added to the tunnel. Presigned S3 URLs are opened by the device and the hostname is covered by the signature, so a URL signed against the compose-internal `minio:9000` is unusable off-box. The alternative — proxying every audio byte through the Node API — was rejected as it doubles bandwidth through the smallest component and defeats the purpose of presigning.
