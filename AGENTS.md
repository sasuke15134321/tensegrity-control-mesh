# TCM v0.6 agent guidance

Purpose: test whether a declared control structure can re-equilibrate after injected control losses.

Input schema: `tcm.control.v0.6`.

Required per control: `id`, `direction`, `weight`, `capacity`.

- `direction`: `negative` or `positive`. This is an abstract balance-axis sign, not physical direction.
- `mode`: `fixed` or `adaptive`.
- `adaptive`: may change only inside declared `min_weight` / `max_weight`.
- `hard=true`: never adjusted; excluded from failure injection unless explicitly requested.
- `inspection.max_depth`: ordered failure depth to test.

Do not infer semantic substitutability. The caller must declare direction, adjustability, bounds, and hard controls.

Output is structural evidence only. `feasible` does not authorize execution. `survival_ratio` is not a probability.
