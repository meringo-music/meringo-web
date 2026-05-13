# OG Image Generator

`assets/og.png` (1200×630) is the social-share image referenced by `<meta property="og:image">` and `<meta name="twitter:image">`. It is rendered from `tools/og/og.html` via headless Edge — there is no Photoshop / Figma source.

## Regenerate

From the repo root, in PowerShell:

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --headless=new --disable-gpu --hide-scrollbars `
  --window-size=1200,630 --force-device-scale-factor=1 `
  --virtual-time-budget=15000 `
  --screenshot="C:\Source\meringo-web\assets\og.png" `
  "file:///C:/Source/meringo-web/tools/og/og.html"
```

Then verify the PNG opens correctly and commit both files together if you edited the HTML.

## What's in the render

- Background: Deep Velvet (`#1A0E2E`) with velvet-purple radial glow upper-left and gold radial glow lower-right
- Brand mark: waveform-in-circle (matches the favicon / `assets/logo.svg`)
- Wordmark: "Meringo" in Cormorant Garamond, 156px
- Ornament: gold dot between tapered gradient lines (matches site dividers)
- Tagline: italic Cormorant
- Tech chips: FLAC · ALAC, 24-BIT / 192 KHZ, BIT-PERFECT, JELLYFIN · SUBSONIC
- Right column: tilted Now Playing device shell (sources `assets/screens/now_playing.png` via relative path)
- Film grain SVG overlay at 4% opacity

## When to regenerate

- Updated Now Playing screenshot
- Tagline or chip copy changed
- Brand assets refreshed
- After any change to `og.html`

The fonts come from Google Fonts CDN; the 15-second `--virtual-time-budget` ensures they load before the screenshot fires.
