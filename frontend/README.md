# BrandPulse frontend

Next.js App Router frontend for BrandPulse AI.

## Modes

- `NEXT_PUBLIC_USE_GOLDEN=true`: reads `contracts/golden/samsung_battery.json` and never spends SerpApi/Groq credits.
- `NEXT_PUBLIC_USE_GOLDEN=false`: uses the typed FastAPI client through the `/api` rewrite.

## Commands

```bash
npm install
npm run generate:types
npm run typecheck
npm run lint
npm test
npm run build
npm run dev
```

Golden journey (Phase 1): `/` → `/analyze` → `/analyze/demo` (simulated progress) → `/dashboard/demo` → `/investigate/demo-signal-battery` → `/evidence/demo-investigation` → source URL. Also `/signals/demo-signal-battery` and `/competitors/demo`.

Golden-only extras (estimate, usage, status, mentions) live in `lib/golden/extras.ts`; the golden JSON contract is unchanged. Component tests render with `react-dom/server` (no DOM library).
