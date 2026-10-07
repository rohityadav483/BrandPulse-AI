# BrandPulse AI — Scoring Contract

Phase 0 defines the deterministic formulas used by later pipeline phases. These functions must remain pure and backend-owned; the frontend only formats their results.

## 1. Growth

For the `(brand, aspect)` negative-mention share:

```text
share_w = n_w / N_w
growth = (share_current + ε) / (share_baseline + ε)
ε = 0.02
```

Only reliably dated `news` and `web` items drive growth. Other source types count toward frequency, cross-source corroboration, and total sample size.

The golden Samsung fixture uses `9/31` versus `2/27`:

```text
((9/31) + 0.02) / ((2/27) + 0.02) = 3.2987 ≈ 3.3×
```

## 2. Signal score

Normalize the four components to `[0,1]`:

```text
G = clamp(log2(growth) / log2(5))
F = clamp(share_current_all / 0.25)
C = distinct negative source types / 4
S = mean negative-class probability

score = 0.35G + 0.20F + 0.25C + 0.20S
```

Flag threshold: `>= 0.60`. Impact is `HIGH` at `>= 0.75`, `MEDIUM` from `0.60` to `<0.75`.

The golden component values reproduce `0.789`, displayed as `0.79`.

## 3. Brand Health

```text
health = round(
  0.35·sentiment +
  0.20·engagement +
  0.25·risk +
  0.20·trend
)
```

Risk is inverted: `100` means no risk. Engagement is a proxy and must be visually marked as lower confidence.

Golden values `72, 81, 64, 76` produce `72.6`, displayed as `73`.

## 4. Investigation confidence

```text
confidence = min(95, round(100 × (
  0.30·independence +
  0.25·agreement +
  0.20·signal_strength +
  0.15·recency +
  0.10·consistency
)))
```

Fewer than two independent supporting sources forces Low confidence. The LLM never supplies or changes this number.

Golden factors reproduce `85.55`, displayed as `86`.

## 5. Net sentiment

```text
net_score = positive% − negative%
```

Range: `-100` to `100`.

Golden checks:

- Camera: `78 − 8 = 70`
- Battery: `12 − 60 = -48`
- Apple battery: `40 − 20 = 20`

## 6. Determinism and ownership

- Backend calculates all scores.
- Inputs and formulas are versioned and testable.
- LLM output cannot invent confidence or numeric scores.
- API DTOs expose computed values; the browser never recomputes them.
