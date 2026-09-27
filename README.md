# Tensegrity Control Mesh v1.0 — Bounded Public Candidate

v1.0 freezes the first public resource envelope before deployment.

## Public candidate limits

- controls: maximum 20
- ordered failure depth: maximum 2
- injected cases: maximum 1,000
- planned paid price: 0.01 USDC per `/inspect`

The price is declared but **not yet enforced** in v1.0. No x402 metadata or
402 payment behavior is claimed until the payment layer is actually implemented.

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

During public-candidate interoperability testing this endpoint remains unpaid.
After public-Internet black-box verification, the intended commercial contract
is 0.01 USDC per inspection.

## Interpretation boundary

TCM returns structural evidence only.

- feasible does not authorize execution
- survival_ratio is not a probability
- TCM does not infer semantic substitutability
- TCM does not mutate the target system

## Next evidence gate

Deploy the exact v1.0 candidate to a public HTTPS endpoint and run
`external_probe.py` against that URL, including `--inject-error`.

Only after that succeeds should x402 payment enforcement be added.
