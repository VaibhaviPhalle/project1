# Source Licenses & Attribution

This project ingests publicly available specifications and documentation. Each
ingested source is governed by its own license, which is recorded here for
attribution and reuse compliance.

## IETF RFCs

Every IETF RFC ingested by this project is governed by the **IETF Trust
Legal Provisions (BCP 78)**. RFCs are effectively in the public domain —
they may be reproduced and redistributed without modification, with
attribution to the IETF Trust.

Ingested RFCs in this corpus:

- RFC 6749 — The OAuth 2.0 Authorization Framework
- RFC 6750 — OAuth 2.0 Bearer Token Usage
- RFC 6819 — OAuth 2.0 Threat Model and Security Considerations
- RFC 7519 — JSON Web Token (JWT)
- RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol
- RFC 7592 — OAuth 2.0 DCR Management Protocol
- RFC 7636 — Proof Key for Code Exchange (PKCE)
- RFC 8252 — OAuth 2.0 for Native Apps (BCP 212)
- RFC 8628 — OAuth 2.0 Device Authorization Grant
- RFC 8693 — OAuth 2.0 Token Exchange
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens

Source: <https://www.rfc-editor.org/>
Legal: <https://trustee.ietf.org/license-info/>

## Future sources (not yet ingested)

- **OpenID Connect Core 1.0** — © OpenID Foundation, redistribution per the
  OpenID Foundation IPR policy.
- **SAML 2.0 Core** — © OASIS Open, redistribution per the OASIS IPR policy.
- **Keycloak Server Administration Guide** — Apache License 2.0, © Red Hat.
- **Auth0 documentation** — © Auth0 Inc.; cited under fair-use educational
  reproduction. Excerpts are quoted with attribution; the full corpus is not
  redistributed.

The downloader records the source URL, retrieval timestamp, and SHA-256 hash
of every fetched file in `data/raw/<doc_id>.<ext>.meta.json`, and the manifest
at `data/processed/manifest.json` records the same per-document.
