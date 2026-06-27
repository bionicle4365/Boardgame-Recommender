import os
import json
import boto3
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_OUTPUT_BUCKET_NAME", "boardgame-app")
S3_KEY = "data/active_previews.json"

s3 = boto3.client('s3')

def get_active_previews():
    previews = []
    with sync_playwright() as p:
        logger.info("Launching chromium...")
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        logger.info("Navigating to https://boardgamegeek.com/previews ...")
        page.goto("https://boardgamegeek.com/previews", wait_until="domcontentloaded")
        
        logger.info("Extracting preview data...")
        # Evaluate a JS snippet to extract preview IDs
        # The exact DOM structure isn't guaranteed, but BGG previews page typically has links to /preview/
        
        # We try to extract from __PRELOADED_STATE__ if available (common in BGG Angular/React refactors)
        state_data = page.evaluate("""
            () => {
                if (window.__PRELOADED_STATE__) {
                    return window.__PRELOADED_STATE__;
                }
                if (window.Geek && window.Geek.geekPreviews) {
                    return window.Geek.geekPreviews;
                }
                return null;
            }
        """)
        
        if state_data:
            # If we found preloaded state, it might have preview items
            logger.info("Found preloaded state, but we fall back to link extraction for resilience.")
            
        # Fallback: extract links
        links = page.locator('a[href*="/preview/"]').element_handles()
        unique_links = {}
        for link in links:
            href = link.get_attribute("href")
            text = link.inner_text().strip()
            
            # href looks like /preview/gencon2024
            # We don't get the preview_id integer directly from the link usually, but wait, 
            # maybe the API doesn't use the integer, or maybe the integer is the only thing the API takes?
            # Actually, `GET /api/geekpreviewitems?previewid={id}` requires the integer ID.
            # If we can't find the integer ID easily, we might need to fetch the HTML of the preview page itself!
            if text and href and href not in unique_links:
                unique_links[href] = text
                
        # To get the actual previewid, we might need to visit each preview URL and extract the previewid
        for href, name in unique_links.items():
            if name.lower() in ["previews", "archive"]:
                continue
            
            logger.info(f"Visiting preview page: {href}")
            full_url = f"https://boardgamegeek.com{href}"
            page.goto(full_url, wait_until="domcontentloaded")
            
            preview_id = page.evaluate("""
                () => {
                    // Try to find the previewid in the DOM
                    // Often embedded in a script tag or global variable
                    if (window.Geek && window.Geek.previewId) return window.Geek.previewId;
                    
                    // Fallback: look for API calls or elements with data-previewid
                    let el = document.querySelector('[data-previewid]');
                    if (el) return parseInt(el.getAttribute('data-previewid'));
                    
                    // Fallback: check scripts
                    let scripts = document.querySelectorAll('script');
                    for (let s of scripts) {
                        let match = s.innerText.match(/previewid["']?\\s*:\\s*(\\d+)/i);
                        if (match) return parseInt(match[1]);
                    }
                    return null;
                }
            """)
            
            if preview_id:
                logger.info(f"Discovered preview {name} with ID {preview_id}")
                previews.append({
                    "name": name,
                    "preview_id": preview_id,
                    "href": href,
                    "game_ids": []
                })
            else:
                logger.warning(f"Could not find preview_id for {name}")

        browser.close()
        
    return previews

def main():
    previews = get_active_previews()
    if previews:
        logger.info(f"Saving {len(previews)} previews to S3...")
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=S3_KEY,
            Body=json.dumps(previews),
            ContentType='application/json'
        )
        logger.info("Done.")
    else:
        logger.info("No active previews found.")

if __name__ == "__main__":
    main()
