#!/usr/bin/env python3
"""
Automated Table Tent & QR Code Generator for Board Game Cafe & Bar Edition.

Generates high-resolution, print-ready vector SVG and printable HTML table tents
with cafe branding, table number badge, Wi-Fi credentials, and QR code leading directly
to each table's patron portal.
"""

import os
import sys
import argparse
import json
import xml.etree.ElementTree as ET

try:
    import qrcode
    import qrcode.image.svg
except ImportError:
    qrcode = None


def generate_qr_svg_path(url):
    """Generates an SVG path element representing the QR code for a given URL."""
    if qrcode is not None:
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(url, image_factory=factory, box_size=10, border=1)
        svg_bytes = img.to_string()
        # Parse and extract viewBox and path
        root = ET.fromstring(svg_bytes)
        view_box = root.attrib.get('viewBox', '0 0 350 350')
        path_elem = root.find('{http://www.w3.org/2000/svg}path') or root.find('path')
        path_d = path_elem.attrib.get('d', '') if path_elem is not None else ''
        return view_box, path_d
    else:
        # Graceful placeholder fallback if qrcode is not installed (e.g. minimal or test environments)
        return '0 0 350 350', 'M 20 20 L 330 20 L 330 330 L 20 330 Z'


def generate_table_tent_svg(cafe_id, cafe_name, table_num, target_url, wifi_ssid="", wifi_password="", tagline=""):
    """
    Generates a print-ready vector SVG for a folding table tent (US Letter / A4 width).
    Standard foldable tent card with front and back mirrored or duplicate panels.
    """
    view_box, path_d = generate_qr_svg_path(target_url)

    wifi_info = ""
    if wifi_ssid:
        wifi_info = f"Wi-Fi: {wifi_ssid}"
        if wifi_password:
            wifi_info += f"  •  Pass: {wifi_password}"

    tagline_text = tagline or "Scan to find your table's perfect game in 30 seconds"

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 1100" width="800" height="1100">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&amp;display=swap');
      .font-main {{ font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif; }}
      .cafe-title {{ font-size: 26px; font-weight: 800; fill: #1e1b4b; text-anchor: middle; }}
      .table-badge-bg {{ fill: #4f46e5; rx: 12px; }}
      .table-badge-text {{ font-size: 18px; font-weight: 700; fill: #ffffff; text-anchor: middle; letter-spacing: 0.05em; }}
      .cta-heading {{ font-size: 20px; font-weight: 700; fill: #0f172a; text-anchor: middle; }}
      .cta-sub {{ font-size: 13px; font-weight: 500; fill: #64748b; text-anchor: middle; }}
      .wifi-text {{ font-size: 13px; font-weight: 600; fill: #334155; text-anchor: middle; }}
      .powered-by {{ font-size: 10px; font-weight: 500; fill: #94a3b8; text-anchor: middle; }}
      .fold-line {{ stroke: #cbd5e1; stroke-width: 1.5; stroke-dasharray: 6,4; }}
      .cut-line {{ stroke: #94a3b8; stroke-width: 1; stroke-dasharray: 3,3; }}
    </style>
    <linearGradient id="headerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4f46e5"/>
      <stop offset="100%" stop-color="#818cf8"/>
    </linearGradient>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-opacity="0.08"/>
    </filter>
  </defs>

  <!-- Background Canvas -->
  <rect width="800" height="1100" fill="#f8fafc"/>

  <!-- Top Panel (Front Face) -->
  <g transform="translate(100, 80)">
    <!-- Card Frame -->
    <rect width="600" height="420" rx="16" fill="#ffffff" stroke="#e2e8f0" stroke-width="2" filter="url(#shadow)"/>
    <rect width="600" height="8" rx="4" fill="url(#headerGrad)"/>

    <!-- Header -->
    <text x="300" y="52" class="font-main cafe-title">{cafe_name}</text>
    
    <!-- Table Badge -->
    <rect x="230" y="70" width="140" height="32" class="table-badge-bg"/>
    <text x="300" y="92" class="font-main table-badge-text">TABLE {table_num}</text>

    <!-- QR Code Embed -->
    <g transform="translate(210, 115) scale(0.52)">
      <svg viewBox="{view_box}" width="350" height="350">
        <path d="{path_d}" fill="#0f172a"/>
      </svg>
    </g>

    <!-- Call to Action -->
    <text x="300" y="325" class="font-main cta-heading">🎲 Find What to Play</text>
    <text x="300" y="348" class="font-main cta-sub">{tagline_text}</text>

    <!-- Wi-Fi Strip -->
    <rect x="50" y="365" width="500" height="32" rx="8" fill="#f1f5f9"/>
    <text x="300" y="386" class="font-main wifi-text">📶 {wifi_info or "Ask staff for Wi-Fi access"}</text>
  </g>

  <!-- Folding Line Indicator -->
  <line x1="40" y1="550" x2="760" y2="550" class="fold-line"/>
  <text x="400" y="545" class="font-main" font-size="11" fill="#94a3b8" text-anchor="middle">✂️ FOLD HERE FOR STANDING TENT CARD</text>

  <!-- Bottom Panel (Back Face - Inverted for Folding or Duplicate) -->
  <g transform="translate(100, 600)">
    <!-- Card Frame -->
    <rect width="600" height="420" rx="16" fill="#ffffff" stroke="#e2e8f0" stroke-width="2" filter="url(#shadow)"/>
    <rect width="600" height="8" rx="4" fill="url(#headerGrad)"/>

    <!-- Header -->
    <text x="300" y="52" class="font-main cafe-title">{cafe_name}</text>
    
    <!-- Table Badge -->
    <rect x="230" y="70" width="140" height="32" class="table-badge-bg"/>
    <text x="300" y="92" class="font-main table-badge-text">TABLE {table_num}</text>

    <!-- QR Code Embed -->
    <g transform="translate(210, 115) scale(0.52)">
      <svg viewBox="{view_box}" width="350" height="350">
        <path d="{path_d}" fill="#0f172a"/>
      </svg>
    </g>

    <!-- Call to Action -->
    <text x="300" y="325" class="font-main cta-heading">🎲 Find What to Play</text>
    <text x="300" y="348" class="font-main cta-sub">{tagline_text}</text>

    <!-- Wi-Fi Strip -->
    <rect x="50" y="365" width="500" height="32" rx="8" fill="#f1f5f9"/>
    <text x="300" y="386" class="font-main wifi-text">📶 {wifi_info or "Ask staff for Wi-Fi access"}</text>
  </g>

  <!-- Footer branding -->
  <text x="400" y="1075" class="font-main powered-by">Powered by Meeple Manifesto Sommelier • Table URL: {target_url}</text>
</svg>
'''
    return svg_content


def generate_printable_html_sheet(cafe_id, cafe_name, table_items, wifi_ssid="", wifi_password="", tagline=""):
    """
    Generates a single master printable HTML file containing all table tents with
    clean print stylesheets and page breaks.
    """
    cards_html = []
    for item in table_items:
        table_num = item['table']
        svg_content = item['svg']
        cards_html.append(f'''
        <div class="sheet-page">
            {svg_content}
        </div>
        ''')

    all_cards = "\n".join(cards_html)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{cafe_name} - Printable Table Tents</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background-color: #f1f5f9;
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #0f172a;
        }}
        .print-toolbar {{
            background: #ffffff;
            padding: 16px 24px;
            border-radius: 12px;
            max-width: 800px;
            margin: 0 auto 30px auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .print-btn {{
            background: #4f46e5;
            color: #ffffff;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        .print-btn:hover {{
            background: #4338ca;
        }}
        .sheet-container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        .sheet-page {{
            background: #ffffff;
            margin-bottom: 30px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            border-radius: 8px;
            overflow: hidden;
            page-break-after: always;
            break-after: page;
        }}
        .sheet-page svg {{
            display: block;
            width: 100%;
            height: auto;
        }}
        @media print {{
            body {{
                background: none;
                padding: 0;
            }}
            .print-toolbar {{
                display: none;
            }}
            .sheet-container {{
                max-width: 100%;
                margin: 0;
            }}
            .sheet-page {{
                margin-bottom: 0;
                box-shadow: none;
                border-radius: 0;
                page-break-after: always;
                break-after: page;
            }}
        }}
    </style>
</head>
<body>
    <div class="print-toolbar">
        <div>
            <h2 style="margin: 0 0 4px 0;">{cafe_name} Table Tent QR Kit</h2>
            <p style="margin: 0; color: #64748b; font-size: 0.9rem;">{len(table_items)} table tents ready to print</p>
        </div>
        <button class="print-btn" onclick="window.print()">🖨️ Print All Table Tents</button>
    </div>

    <div class="sheet-container">
        {all_cards}
    </div>
</body>
</html>
'''
    return html


def generate_qr_bundle(cafe_id, name, table_count=20, base_url="https://www.meeplemanifesto.com/cafe",
                       wifi_ssid="", wifi_password="", tagline="", output_dir=None):
    """
    Main entry point for generating the complete table tent kit for a venue.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'scratch', 'table_tents', cafe_id)

    os.makedirs(output_dir, exist_ok=True)

    table_items = []
    generated_files = []

    for t in range(1, table_count + 1):
        target_url = f"{base_url.rstrip('/')}/{cafe_id}?table={t}"
        svg = generate_table_tent_svg(
            cafe_id=cafe_id,
            cafe_name=name,
            table_num=t,
            target_url=target_url,
            wifi_ssid=wifi_ssid,
            wifi_password=wifi_password,
            tagline=tagline
        )

        svg_filename = f"table_{t}.svg"
        svg_path = os.path.join(output_dir, svg_filename)
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg)

        table_items.append({'table': t, 'url': target_url, 'svg': svg, 'file': svg_filename})
        generated_files.append(svg_path)

    # Generate print sheet HTML
    print_sheet_html = generate_printable_html_sheet(
        cafe_id=cafe_id,
        cafe_name=name,
        table_items=table_items,
        wifi_ssid=wifi_ssid,
        wifi_password=wifi_password,
        tagline=tagline
    )
    print_sheet_path = os.path.join(output_dir, "print_all_tables.html")
    with open(print_sheet_path, 'w', encoding='utf-8') as f:
        f.write(print_sheet_html)
    generated_files.append(print_sheet_path)

    # Save bundle manifest JSON
    manifest = {
        'cafe_id': cafe_id,
        'name': name,
        'table_count': table_count,
        'base_url': base_url,
        'wifi_ssid': wifi_ssid,
        'output_dir': os.path.abspath(output_dir),
        'tables': [{'table': item['table'], 'url': item['url'], 'svg_file': item['file']} for item in table_items],
        'print_sheet': "print_all_tables.html"
    }
    manifest_path = os.path.join(output_dir, "bundle_manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    generated_files.append(manifest_path)

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate print-ready QR table tents for board game cafes.")
    parser.add_argument("--cafe-id", required=True, help="Cafe vanity slug / ID (e.g. the-malt-and-meeple)")
    parser.add_argument("--name", required=True, help="Display name of the venue (e.g. 'The Malt & Meeple')")
    parser.add_argument("--tables", type=int, default=20, help="Total number of tables (default: 20)")
    parser.add_argument("--base-url", default="https://www.meeplemanifesto.com/cafe", help="Base URL for tables")
    parser.add_argument("--wifi-ssid", default="", help="Guest Wi-Fi SSID")
    parser.add_argument("--wifi-password", default="", help="Guest Wi-Fi Password")
    parser.add_argument("--tagline", default="", help="Custom welcoming tagline")
    parser.add_argument("--output-dir", default=None, help="Output directory")

    args = parser.parse_args()

    if qrcode is None:
        print("Note: 'qrcode' package is not installed. Generating table tents with placeholder QR paths.", file=sys.stderr)
        print("Run 'pip install qrcode' for scannable QR codes.", file=sys.stderr)

    print(f"Generating table tents for '{args.name}' ({args.cafe_id}) - {args.tables} tables...")
    manifest = generate_qr_bundle(
        cafe_id=args.cafe_id,
        name=args.name,
        table_count=args.tables,
        base_url=args.base_url,
        wifi_ssid=args.wifi_ssid,
        wifi_password=args.wifi_password,
        tagline=args.tagline,
        output_dir=args.output_dir
    )
    print(f"Successfully generated {args.tables} table tents!")
    print(f"Print sheet: {os.path.join(manifest['output_dir'], manifest['print_sheet'])}")


if __name__ == "__main__":
    main()
