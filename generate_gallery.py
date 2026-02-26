#!/usr/bin/env python3
"""
generate_gallery.py
───────────────────
Fetches a public Google Photos shared album, extracts all image URLs,
and writes a self-contained interests.html gallery page.

Usage:
    python generate_gallery.py --album "https://photos.app.goo.gl/XXXXXX"
    python generate_gallery.py --album "https://photos.app.goo.gl/XXXXXX" --out interests.html
    python generate_gallery.py --album "https://photos.app.goo.gl/XXXXXX" --title "Hiking & Travel"

Requirements:
    pip install requests beautifulsoup4

How it works:
    Google Photos public albums embed all image metadata directly in the
    page's HTML as a nested JavaScript data array. This script fetches that
    page, parses out every lh3.googleusercontent.com URL, requests
    high-resolution versions, and builds a static masonry gallery.
"""

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run:  pip install requests beautifulsoup4")
    sys.exit(1)


# ── Image extraction ──────────────────────────────────────────────────────────

def fetch_album_page(url: str) -> str:
    """
    Follow redirects (goo.gl short links) and return the final page HTML.
    Google Photos needs a browser-like User-Agent or it returns a redirect loop.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_images(html: str) -> list[dict]:
    """
    Google Photos embeds image data in the page as a large JS data structure.
    Image URLs follow the pattern: https://lh3.googleusercontent.com/pw/...
    Each URL can be suffixed with sizing parameters:
        =w800       → width 800px
        =h600       → height 600px
        =w800-h600  → fit within 800×600
        =d           → original download size

    Returns a list of dicts: {url, width, height, alt}
    """
    # Primary pattern: find all lh3.googleusercontent.com/pw/ URLs in the raw HTML
    # These are embedded as JSON strings inside the page's <script> data
    raw_urls = re.findall(
        r'https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_\-]+',
        html
    )

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for u in raw_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if not unique_urls:
        # Fallback: try broader googleusercontent pattern (some albums use different paths)
        raw_urls = re.findall(
            r'https://lh3\.googleusercontent\.com/[A-Za-z0-9_\-/]+',
            html
        )
        seen = set()
        for u in raw_urls:
            if u not in seen and len(u) > 60:  # filter out short icon URLs
                seen.add(u)
                unique_urls.append(u)

    if not unique_urls:
        print("⚠️  No images found. The album may be private or the URL may be incorrect.")
        print("   Make sure the album is set to 'Anyone with the link can view'.")
        sys.exit(1)

    # Try to extract width/height metadata from the JS data blob
    # Google encodes image metadata as arrays: [url, width, height, ...]
    meta_pattern = re.compile(
        r'"(https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_\-]+)"'
        r'[^]]*?,(\d{3,5}),(\d{3,5})'
    )
    meta_map = {}
    for match in meta_pattern.finditer(html):
        url, w, h = match.group(1), int(match.group(2)), int(match.group(3))
        meta_map[url] = {"width": w, "height": h}

    images = []
    for url in unique_urls:
        meta = meta_map.get(url, {})
        images.append({
            "base_url": url,
            # Display URL: request a 1200px-wide version for full quality
            "display_url": url + "=w1200",
            # Thumbnail URL: 600px wide for fast initial load
            "thumb_url": url + "=w600",
            "width": meta.get("width", 0),
            "height": meta.get("height", 0),
            "alt": "Photo",
        })

    print(f"✓ Found {len(images)} images")
    return images


def extract_album_title(html: str) -> str | None:
    """Try to pull the album title from the page <title> or og:title tag."""
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        # Strip " - Google Photos" suffix
        return re.sub(r"\s*[-–]\s*Google Photos$", "", t).strip() or None
    return None


# ── HTML generation ───────────────────────────────────────────────────────────

def build_gallery_html(
    images: list[dict],
    album_url: str,
    album_title: str = "Photos",
    page_title: str = "Interests",
) -> str:
    """Render a complete self-contained interests.html with a masonry lightbox gallery."""

    # Build the JS image data array
    js_images = json.dumps(
        [{"src": img["display_url"], "thumb": img["thumb_url"]} for img in images],
        indent=2
    )

    # Build the thumbnail <figure> elements
    figures = []
    for i, img in enumerate(images):
        figures.append(
            f'      <figure class="gal-item" data-index="{i}">'
            f'<img src="{img["thumb_url"]}" alt="{img["alt"]}" loading="lazy" /></figure>'
        )
    figures_html = "\n".join(figures)

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>{page_title} &mdash; Lucas Hinsenkamp, PhD</title>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
      <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Mono:wght@300;400&display=swap" rel="stylesheet" />
      <style>
        :root {{
          --ink:    #1a1a18;
          --paper:  #f7f5f0;
          --muted:  #8a8880;
          --rule:   #dedad4;
          --accent: #2d5a3d;
          --serif:  'Cormorant Garamond', Georgia, serif;
          --mono:   'DM Mono', 'Courier New', monospace;
          --max:    720px;
        }}
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{ font-size: 18px; scroll-behavior: smooth; }}
        body {{ background: var(--paper); color: var(--ink); font-family: var(--serif); font-weight: 300; line-height: 1.7; min-height: 100vh; display: flex; flex-direction: column; }}
        main {{ flex: 1; }}
        .container {{ max-width: var(--max); margin: 0 auto; padding: 0 2rem; }}

        /* Nav */
        nav {{ position: sticky; top: 0; z-index: 100; background: rgba(247,245,240,0.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--rule); padding: 1rem 0; }}
        nav .container {{ display: flex; justify-content: space-between; align-items: baseline; }}
        .nav-name {{ font-size: 0.78rem; font-family: var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink); text-decoration: none; }}
        .nav-links {{ display: flex; gap: 2rem; list-style: none; }}
        .nav-links a {{ font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); text-decoration: none; transition: color 0.2s; }}
        .nav-links a:hover {{ color: var(--ink); }}
        .nav-links a.active {{ color: var(--ink); border-bottom: 1px solid var(--ink); padding-bottom: 1px; }}

        /* Page header */
        .page-header {{ padding: 5rem 0 3.5rem; border-bottom: 1px solid var(--rule); }}
        .eyebrow {{ font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); margin-bottom: 1rem; }}
        h1 {{ font-size: clamp(2.2rem, 6vw, 3.5rem); font-weight: 300; line-height: 1.1; letter-spacing: -0.01em; }}
        h1 em {{ font-style: italic; }}
        .page-header p.sub {{ font-size: 1.05rem; color: #5a5a58; max-width: 500px; margin-top: 1.25rem; line-height: 1.75; }}
        .album-link {{ display: inline-block; margin-top: 1.25rem; font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); text-decoration: none; border-bottom: 1px solid var(--rule); padding-bottom: 2px; transition: color 0.2s, border-color 0.2s; }}
        .album-link:hover {{ color: var(--accent); border-color: var(--accent); }}

        /* Section */
        .section-wrap {{ padding: 3.5rem 0; }}
        .section-header {{ display: flex; align-items: baseline; gap: 1.5rem; margin-bottom: 2.5rem; }}
        .section-label {{ font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }}
        .section-rule {{ flex: 1; height: 1px; background: var(--rule); }}
        .image-count {{ font-family: var(--mono); font-size: 0.65rem; color: var(--muted); }}

        /* Masonry gallery */
        .gallery {{
          columns: 3 160px;
          column-gap: 0.6rem;
        }}
        .gal-item {{
          break-inside: avoid;
          margin-bottom: 0.6rem;
          cursor: pointer;
          overflow: hidden;
          border-radius: 2px;
          background: var(--rule);
        }}
        .gal-item img {{
          display: block;
          width: 100%;
          height: auto;
          transition: transform 0.35s ease, opacity 0.2s;
          opacity: 0;
        }}
        .gal-item img.loaded {{ opacity: 1; }}
        .gal-item:hover img {{ transform: scale(1.03); }}

        /* Lightbox */
        #lightbox {{
          display: none;
          position: fixed;
          inset: 0;
          background: rgba(20,20,18,0.96);
          z-index: 1000;
          align-items: center;
          justify-content: center;
          flex-direction: column;
        }}
        #lightbox.open {{ display: flex; }}
        #lb-img {{
          max-width: min(92vw, 1100px);
          max-height: 85vh;
          object-fit: contain;
          border-radius: 2px;
          display: block;
        }}
        #lb-counter {{
          font-family: var(--mono);
          font-size: 0.68rem;
          color: rgba(255,255,255,0.4);
          letter-spacing: 0.1em;
          margin-top: 1rem;
        }}
        .lb-btn {{
          position: fixed;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: rgba(255,255,255,0.5);
          font-size: 2rem;
          cursor: pointer;
          padding: 1rem;
          line-height: 1;
          transition: color 0.2s;
          font-family: var(--mono);
        }}
        .lb-btn:hover {{ color: #fff; }}
        #lb-prev {{ left: 1rem; }}
        #lb-next {{ right: 1rem; }}
        #lb-close {{
          position: fixed;
          top: 1.25rem;
          right: 1.5rem;
          background: none;
          border: none;
          color: rgba(255,255,255,0.5);
          font-size: 1.5rem;
          cursor: pointer;
          font-family: var(--mono);
          transition: color 0.2s;
        }}
        #lb-close:hover {{ color: #fff; }}

        /* Interest blurbs */
        .interests-section {{ padding: 3.5rem 0; border-bottom: 1px solid var(--rule); }}
        .interest-entry {{ padding: 2rem 0; border-top: 1px solid var(--rule); display: grid; grid-template-columns: 140px 1fr; gap: 0 2rem; }}
        .interest-entry:first-of-type {{ border-top: none; padding-top: 0; }}
        .interest-label {{ font-family: var(--mono); font-size: 0.7rem; color: var(--muted); padding-top: 0.25rem; }}
        .interest-body h3 {{ font-size: 1.15rem; font-weight: 400; margin-bottom: 0.4rem; }}
        .interest-body p {{ font-size: 0.95rem; color: #4a4a48; line-height: 1.75; }}

        /* Footer */
        footer {{ padding: 3rem 0; border-top: 1px solid var(--rule); }}
        footer .container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }}
        .footer-copy {{ font-family: var(--mono); font-size: 0.68rem; color: var(--muted); letter-spacing: 0.06em; }}
        .footer-links {{ display: flex; gap: 1.5rem; list-style: none; }}
        .footer-links a {{ font-family: var(--mono); font-size: 0.68rem; color: var(--muted); text-decoration: none; letter-spacing: 0.08em; text-transform: uppercase; transition: color 0.2s; }}
        .footer-links a:hover {{ color: var(--ink); }}

        @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(18px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .fade-up {{ opacity: 0; animation: fadeUp 0.6s ease forwards; }}
        .delay-1 {{ animation-delay: 0.1s; }}
        .delay-2 {{ animation-delay: 0.2s; }}

        @media (max-width: 540px) {{
          nav .container {{ flex-direction: column; gap: 0.75rem; }}
          .nav-links {{ gap: 1.25rem; }}
          .gallery {{ columns: 2 120px; }}
          .interest-entry {{ grid-template-columns: 1fr; gap: 0.3rem; }}
          .lb-btn {{ font-size: 1.5rem; padding: 0.5rem; }}
        }}
      </style>
    </head>
    <body>

      <nav>
        <div class="container">
          <a class="nav-name" href="index.html">Lucas Hinsenkamp</a>
          <ul class="nav-links">
            <li><a href="index.html">About</a></li>
            <li><a href="cv.html">CV</a></li>
            <li><a href="blog.html">Writing</a></li>
            <li><a href="interests.html" class="active">Interests</a></li>
          </ul>
        </div>
      </nav>

      <main>
        <div class="container">

          <div class="page-header">
            <p class="eyebrow fade-up">Personal</p>
            <h1 class="fade-up delay-1">Outside<br /><em>the work</em></h1>
            <p class="sub fade-up delay-2">The things that refuel me, keep me curious, and occasionally make their way into how I think about problems.</p>
          </div>

          <!-- ── Personal interests ── -->
          <div class="interests-section">
            <div class="section-header">
              <span class="section-label">Interests</span>
              <span class="section-rule"></span>
            </div>

            <!-- Replace these entries with your own -->
            <div class="interest-entry">
              <div class="interest-label">Interest one</div>
              <div class="interest-body">
                <h3>Title of Interest</h3>
                <p>A sentence or two about what draws you to this. Keep it personal — this is where you get to sound like a human, not a resume.</p>
              </div>
            </div>

            <div class="interest-entry">
              <div class="interest-label">Interest two</div>
              <div class="interest-body">
                <h3>Title of Interest</h3>
                <p>What do you actually do, and why does it matter to you? The more specific, the more memorable.</p>
              </div>
            </div>

            <div class="interest-entry">
              <div class="interest-label">Interest three</div>
              <div class="interest-body">
                <h3>Title of Interest</h3>
                <p>Maybe something unexpected — an interest that surprises people or gives a different angle on who you are.</p>
              </div>
            </div>
          </div>

          <!-- ── Photo gallery ── -->
          <div class="section-wrap">
            <div class="section-header">
              <span class="section-label">{album_title}</span>
              <span class="section-rule"></span>
              <span class="image-count">{len(images)} photos</span>
            </div>

            <div class="gallery">
    {figures_html}
            </div>

            <a class="album-link" href="{album_url}" target="_blank" rel="noopener">
              View full album in Google Photos &rarr;
            </a>
          </div>

        </div>
      </main>

      <!-- Lightbox -->
      <div id="lightbox" role="dialog" aria-modal="true" aria-label="Photo viewer">
        <button id="lb-close" aria-label="Close">&times;</button>
        <button class="lb-btn" id="lb-prev" aria-label="Previous">&#8592;</button>
        <img id="lb-img" src="" alt="" />
        <p id="lb-counter"></p>
        <button class="lb-btn" id="lb-next" aria-label="Next">&#8594;</button>
      </div>

      <footer>
        <div class="container">
          <p class="footer-copy">&copy; 2025 Lucas Hinsenkamp</p>
          <ul class="footer-links">
            <li><a href="mailto:hinsenkamp@gmail.com">Email</a></li>
            <li><a href="https://linkedin.com/in/lucashinsenkamp" target="_blank" rel="noopener">LinkedIn</a></li>
          </ul>
        </div>
      </footer>

      <script>
        // ── Lazy-load images ──────────────────────────────────────────────────
        document.querySelectorAll('.gal-item img').forEach(img => {{
          if (img.complete) {{ img.classList.add('loaded'); }}
          else {{ img.addEventListener('load', () => img.classList.add('loaded')); }}
        }});

        // ── Image data ───────────────────────────────────────────────────────
        const IMAGES = {js_images};

        // ── Lightbox ─────────────────────────────────────────────────────────
        const lb       = document.getElementById('lightbox');
        const lbImg    = document.getElementById('lb-img');
        const lbClose  = document.getElementById('lb-close');
        const lbPrev   = document.getElementById('lb-prev');
        const lbNext   = document.getElementById('lb-next');
        const lbCount  = document.getElementById('lb-counter');
        let current    = 0;

        function openLightbox(index) {{
          current = index;
          showImage();
          lb.classList.add('open');
          document.body.style.overflow = 'hidden';
        }}

        function closeLightbox() {{
          lb.classList.remove('open');
          document.body.style.overflow = '';
        }}

        function showImage() {{
          lbImg.src = IMAGES[current].src;
          lbCount.textContent = (current + 1) + ' / ' + IMAGES.length;
        }}

        function prev() {{ current = (current - 1 + IMAGES.length) % IMAGES.length; showImage(); }}
        function next() {{ current = (current + 1) % IMAGES.length; showImage(); }}

        document.querySelectorAll('.gal-item').forEach(fig => {{
          fig.addEventListener('click', () => openLightbox(parseInt(fig.dataset.index)));
        }});

        lbClose.addEventListener('click', closeLightbox);
        lbPrev.addEventListener('click', prev);
        lbNext.addEventListener('click', next);

        lb.addEventListener('click', e => {{ if (e.target === lb) closeLightbox(); }});

        document.addEventListener('keydown', e => {{
          if (!lb.classList.contains('open')) return;
          if (e.key === 'ArrowLeft')  prev();
          if (e.key === 'ArrowRight') next();
          if (e.key === 'Escape')     closeLightbox();
        }});
      </script>

    </body>
    </html>
    """)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a static photo gallery from a public Google Photos album."
    )
    parser.add_argument(
        "--album", required=True,
        help="Public Google Photos shared album URL (goo.gl/photos or photos.app.goo.gl link)"
    )
    parser.add_argument(
        "--out", default="interests.html",
        help="Output HTML file path (default: interests.html)"
    )
    parser.add_argument(
        "--title", default=None,
        help="Override the gallery section title (auto-detected from album if omitted)"
    )
    args = parser.parse_args()

    print(f"Fetching album: {args.album}")
    html = fetch_album_page(args.album)

    album_title = args.title or extract_album_title(html) or "Photos"
    print(f"Album title: {album_title}")

    images = extract_images(html)

    out_path = Path(args.out)
    gallery_html = build_gallery_html(
        images=images,
        album_url=args.album,
        album_title=album_title,
    )

    out_path.write_text(gallery_html, encoding="utf-8")
    print(f"✓ Wrote {len(images)} photos → {out_path}")


if __name__ == "__main__":
    main()
