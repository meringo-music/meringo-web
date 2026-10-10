# The share card

`assets/og.png` (1200 × 630) is the image link previews show for every page (`og:image` and
`twitter:image`). It is rendered from `tools/og/og.html`; nothing builds it at serve time.

The card uses only this site's own files: the house kit (`/colors_and_type.css`, `/house.css`)
and its self-hosted fonts. Every word on it is already on the home page: the brand line from the
header, the band's headline and price, and the hero's receipt, hash for hash.

## Rendering it

Serve the repo root over HTTP, so the root-absolute `/colors_and_type.css`, `/house.css` and
`/assets/fonts/` paths resolve. Any static server bound to 127.0.0.1 will do.

Then, from the repo root in another shell, with a throwaway profile so no extension or setting
of yours reaches the render:

    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
      --headless=new --disable-gpu --hide-scrollbars --disable-extensions --no-proxy-server \
      --user-data-dir="$(mktemp -d)" \
      --window-size=1200,630 --force-device-scale-factor=1 \
      --screenshot="$PWD/assets/og.png" \
      http://127.0.0.1:8101/tools/og/og.html

- `--disable-extensions` and `--no-proxy-server`: an extension or a filtering proxy can repaint
  the page before the screenshot is taken.
- `--force-device-scale-factor=1` keeps the file at exactly 1200 × 630.

Look at the PNG before committing it, and keep it under 200 KB.

## When to render it again

- The hero's receipt, the band's headline or the price changes on the home page.
- The house kit changes its plate, gold or type.

If what the card shows changes, change the `og:image:alt` text on the home page to match.
