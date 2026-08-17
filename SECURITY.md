# Security policy

This repository is a production-oriented scaffold, not a completed security
assessment. Before deploying the service on a public or shared network:

- replace all development secrets and disable `AUTH_MODE=dev`;
- configure an OIDC issuer, audience and JWKS endpoint;
- terminate TLS at a trusted reverse proxy;
- restrict MinIO/PostgreSQL/Redis to private networks;
- use a managed secret store and encrypted provider credentials;
- review URL ingestion controls against SSRF and DNS-rebinding attacks;
- configure retention, deletion and audit requirements for audio and voice data;
- run dependency, container and infrastructure scanning;
- perform an application threat model and penetration test.

Report vulnerabilities privately to the repository owner. Do not include API
keys, private podcast URLs, audio recordings or personal data in reports.
