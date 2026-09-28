# Tensegrity Control Mesh v1.0 — Bounded Public Candidate

v1.0 freezes the first public resource envelope before deployment.

## Public candidate limits

- controls: maximum 20
- ordered failure depth: maximum 2
- injected cases: maximum 1,000
- paid price: 0.01 USDC per `/inspect`

`POST /inspect` is priced at **0.01 USDC** and protected by x402 on Base
(`eip155:8453`) in production. Discovery endpoints remain free.

With 20 injectable controls and depth 2, exhaustive ordered inspection is
20 + (20 x 19) = 400 cases, below the service ceiling.

## Free discovery surface

- `GET /`
- `GET /llms.txt`
- `GET /capabilities`
- `GET /schema`
- `GET /openapi.json`

## Compute surface

- `POST /inspect`

Production price: **0.01 USDC per inspection via x402**.
Payment does not authorize execution; TCM returns structural evidence only.

## Interpretation boundary

TCM returns structural evidence only.

- feasible does not authorize execution
- survival_ratio is not a probability
- TCM does not infer semantic substitutability
- TCM does not mutate the target system

## Deployment

Public endpoint:

`https://tensegrity-control-mesh.onrender.com`

Production payment enforcement requires the configured Render environment
variables for the wallet and CDP hosted facilitator credentials.
