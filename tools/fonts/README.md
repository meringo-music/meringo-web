# Self-Hosted Fonts

`assets/fonts/` contains woff2 files for the three site fonts, fetched from Google Fonts and served directly from this origin. The `@font-face` declarations live at the top of `colors_and_type.css`.

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
| Outfit | normal (100-900) | `outfit-latin.woff2` | 32 KB |
| Outfit | normal (100-900) | `outfit-latin-ext.woff2` | 15 KB |
| JetBrains Mono | normal (100-800) | `jetbrainsmono-latin.woff2` | 31 KB |
| JetBrains Mono | normal (100-800) | `jetbrainsmono-latin-ext.woff2` | 12 KB |

Total: ~200 KB across 8 files. Outfit and JetBrains Mono are variable fonts — a single file covers their entire weight range via the `font-weight: 100 900` (or similar) range declaration. Cormorant Garamond's normal style is also variable here; italic ships as a separate font file.

`tools/fonts/google.css` is the raw CSS response Google returned for our font request — kept as an audit trail to verify which `gstatic.com` URLs we extracted from.

## Two fonts are preloaded

`index.html` includes `<link rel="preload">` tags for `cormorant-normal-latin.woff2` and `outfit-latin.woff2` — the two faces visible above the fold (hero title and body / buttons). The other six load lazily via `font-display: swap`.

## Regenerate (when Google publishes new font versions)

```powershell
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
$url = 'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300&family=Outfit:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap'
$css = (Invoke-WebRequest -Uri $url -UserAgent $ua -UseBasicParsing).Content
$css | Out-File -FilePath C:\Source\meringo-web\tools\fonts\google.css -Encoding utf8 -Force
```

Then inspect `google.css`, identify the `latin` and `latin-ext` `woff2` URLs for each family + style, and re-download into `assets/fonts/` using the same naming scheme.

The Google Fonts URLs are versioned (`/v21/...`, `/v24/...`, `/v15/...`) so they're stable. Regenerate only when you want a font update or when extending coverage to new weights / subsets.

## Why not fontsource / npm

The npm fontsource packages would work, but they add a build dependency (npm install + copy step) to what is otherwise a static site with no toolchain. Direct download keeps the workflow `git add . && git push`.
