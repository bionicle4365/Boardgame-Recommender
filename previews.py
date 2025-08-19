from requests_html import HTMLSession
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from datetime import datetime
import os

BASEURL = "https://www.boardgamegeek.com"
session = HTMLSession()

def scrape_previews():
    r = session.get(f"{BASEURL}/previews")
    r.html.render()  # Render the JavaScript

    links = r.html.find("ol")[0].find("li")
    previews = []
    for link in links[::3]:
        spans = link.find('span')
        name = spans[0].text
        date = spans[1].text
        url = f"{BASEURL}{link.find('a', first=True).attrs.get('href')}"
        if datetime.strptime(date, "%b %d, %Y") > datetime.now():
            previews.append({"name": name, "date": date, "url": url})
        else:
            break
    return previews

def download_preview_csv(url):
    download_dir = os.getcwd()
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    # Add logic to download the CSV
    export_button = driver.find_element(By.XPATH, value="//*[@id='mainbody']/div/div/geekpreview/div/ui-view/ui-view/geekpreview-view/div[2]/div/geekpreview-stickymenu/div/div[1]/button")
    export_button.click()
    WebDriverWait(driver, 30).until(
        lambda driver: len(os.listdir(download_dir)) > 0 and \
                       any(".crdownload" not in f for f in os.listdir(download_dir))
    )
    driver.quit()

if __name__ == "__main__":
    previews = scrape_previews()
    for preview in previews:
        download_preview_csv(preview["url"])

