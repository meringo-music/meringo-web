# Self-Hosted Fonts

`assets/fonts/` contains woff2 files for the three site fonts, fetched from Google Fonts and served directly from this origin. The `@font-face` declarations live at the top of `colors_and_type.css`.

**The three families are the app's three.** Cormorant Garamond (display), Inter (UI), Share Tech Mono (technical readouts) are exactly what ships in `core/design/src/main/res/font/` in the app repo. The site ran on Outfit + JetBrains Mono until 2026-07-25; that was never the app's type voice, and because this page embeds real app screenshots the mismatch was visible on the page itself. If the app's font stack changes, this one follows.

## Why self-host

- Removes the `fonts.googleapis.com` round trip (faster first paint by ~100-200 ms)
- Site stays functional if Google Fonts is blocked, slow, or rate-limited
- No third-party `Referer` leakage when visitors load the page

## What's bundled

| Family | Style | File | Approx size |
|---|---|---|---|
| Cormorant Garamond | normal (300-700) | `cormorant-normal-latin.woff2` | 37 KB |
| Cormorant Garamond | normal (300-700) | `cormorant-normal-latin-ext.woff2` | 33 KB |
| Cormorant Garamond | italic (300-700) | `cormorant-italic-latin.woff2` | 22 KB |
| Cormorant Garamond | italic (300-700) | `cormorant-italic-latin-ext.woff2` | 19 KB |
| Inter | normal (100-900) | `inter-latin.woff2` | 47 KB |
| Inter | normal (100-900) | `inter-latin-ext.woff2` | 83 KB |
| Share Tech Mono | normal (400) | `sharetechmono-latin.woff2` | 13 KB |

Total: ~254 KB across 7 files. Inter is a variable font — a single file covers its entire weight range via the `font-weight: 100 900` range declaration. Cormorant Garamond's normal style is also variable here; italic ships as a separate font file.

**Share Tech Mono is the one exception to the variable-font rule.** Google publishes a single 400 face and no `latin-ext` subset — the same single `share_tech_mono_regular.ttf` the app bundles. `colors_and_type.css` declares it as `font-weight: 100 800` anyway, deliberately: that maps every weight the stylesheet asks for onto the one real face instead of letting the browser synthesise a faux-bold. Extended-latin glyphs in mono contexts fall through to the `ui-monospace` stack.

`tools/fonts/google.css` and `tools/fonts/google-app-fonts.css` are the raw CSS responses Google returned for our font requests — kept as an audit trail to verify which `gstatic.com` URLs we extracted from. (`google.css` is the pre-2026-07-25 request, retained for history.)

## Two fonts are preloaded

`index.html` includes `<link rel="preload">` tags for `cormorant-normal-latin.woff2` and `inter-latin.woff2` — the two faces visible above the fold (hero title and body / buttons). The rest load lazily via `font-display: swap`.

## Regenerate (when Google publishes new font versions)

```powershell
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
$url = 'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300&family=Inter:wght@100..900&family=Share+Tech+Mono&display=swap'
$css = (Invoke-WebRequest -Uri $url -UserAgent $ua -UseBasicParsing).Content
$css | Out-File -FilePath C:\Source\meringo-web\tools\fonts\google-app-fonts.css -Encoding utf8 -Force
```

Then inspect `google.css`, identify the `latin` and `latin-ext` `woff2` URLs for each family + style, and re-download into `assets/fonts/` using the same naming scheme.

The Google Fonts URLs are versioned (`/v21/...`, `/v24/...`, `/v15/...`) so they're stable. Regenerate only when you want a font update or when extending coverage to new weights / subsets.

## Why not fontsource / npm

The npm fontsource packages would work, but they add a build dependency (npm install + copy step) to what is otherwise a static site with no toolchain. Direct download keeps the workflow `git add . && git push`.
