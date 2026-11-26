# WorldFeed

Full-screen, zero-overlay feed for playable frontier AI-generated 3D worlds (`mirror` + `embed` tiers only).

- **Controls**: `↑`/`↓` or scroll over the 48px top bar to switch worlds · `WASD` / mouse inside the canvas to play · `L` to like · `G` for original link · `O` for source post · `?` for shortcuts.
- **Defaults**: English UI by default (toggle to Chinese in top bar), pure light-mode 48px header, edge-to-edge live 3D iframe below.

## Build & Verify

Requires **Node.js 22.13+** and **Python 3.9+**.

```bash
npm ci
npm run build   # builds dist/ (set VITE_ATLAS_URL to override Atlas link)
npm run preview
```

To run real Chrome end-to-end verification (with Atlas served on `:8870` and WorldFeed on `:8871`):

```bash
npm run verify
```

Licensed same-origin mirrors and pinned versions are recorded in `scripts/mirrors.config.json` and each mirror's directory under `public/mirrors/`.
