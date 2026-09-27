# TCM v1.0 deployment gate

This repository is the exact public-candidate source.

## Render settings

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check: `/capabilities`

`render.yaml` contains the same settings.

## Pre-deploy gate

Run:

```bash
python -m pytest -q test_agent_declaration_regression.py test_public_bounds.py test_network_blackbox.py
```

Expected: 33 passed.

## Public black-box gate

After Render assigns the HTTPS URL:

```bash
python external_probe.py https://YOUR-SERVICE.onrender.com agent_task_fixture.json
python external_probe.py https://YOUR-SERVICE.onrender.com agent_task_fixture.json --inject-error
```

The second command must report:

- `"ok": true`
- `"network_black_box": true`
- `"recovered_from_422": true`
- `"execution_authorized": false`
- `"safety_probability_available": false`

## Commercial state

Planned price: 0.01 USDC per `/inspect`.

Payment is intentionally **not enforced** in this candidate. Do not advertise
x402 support until the public black-box gate passes and the payment layer is
implemented and independently tested.
