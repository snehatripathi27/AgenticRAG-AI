# BenchLab workspace

React 19 + TypeScript + Vite. Run `npm ci`, then `npm run dev`. Start the Python API on `127.0.0.1:8001` with `benchlab serve`. Vite proxies `/api`. From the repository root, `bash scripts/demo.sh` starts both services.

`npm run build` type-checks/builds the frontend. `npx eslint src/App.tsx` lints the evaluation UI. Production hosting requires an `/api` reverse proxy; Vite is a development server.

Historical RAG components remain in `src/components`. The evaluation interface is `src/App.tsx`; its styles are `src/App.css` and `src/index.css`. See the root README for installation, configuration, and protocols.

The Rollup override pins 4.59.0 while verifying a tree-shaking performance regression observed with 4.64.0. Keep the lockfile when reproducing builds.
