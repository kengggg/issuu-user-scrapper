from __future__ import annotations

import time
import multiprocessing
from pathlib import Path
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from tqdm import tqdm


def _create_requests_session() -> requests.Session:
    """Create a :class:`requests.Session` pre-configured with retries."""

    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        backoff_factor=1.5,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    return session


def download_pdf(url: str, folder: str, link: str) -> None:
    """Download a single PDF file with retry and streaming support."""

    target_dir = Path(folder)
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{link.rstrip('/').split('/')[-1]}.pdf"
    filepath = target_dir / filename

    if filepath.exists():
        # Skip download if the file already exists to avoid unnecessary work.
        return

    session = _create_requests_session()

    try:
        with session.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            with filepath.open("wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
    except RequestException as exc:
        if filepath.exists():
            filepath.unlink()
        print(f"Failed to download PDF from {url}: {exc}")


def _build_chrome_options(headless: bool = True) -> Options:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return options


_CHROME_DRIVER_PATH: str | None = None


def _get_chromedriver_path() -> str:
    """Return the cached ChromeDriver path, installing it lazily if necessary."""

    global _CHROME_DRIVER_PATH
    if _CHROME_DRIVER_PATH is None:
        _CHROME_DRIVER_PATH = ChromeDriverManager().install()
    return _CHROME_DRIVER_PATH


def download_link_pdf(link: str, save_folder: str) -> None:
    chrome_options = _build_chrome_options()

    try:
        driver = webdriver.Chrome(service=Service(_get_chromedriver_path()), options=chrome_options)
    except WebDriverException as exc:
        print(f"Unable to start ChromeDriver for link {link}: {exc}")
        return

    try:
        driver.get('https://issuudownload.com/')

        input_field = WebDriverWait(driver, 50).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '#DocumentUrl'))
        )

        input_field.clear()
        input_field.send_keys(link)

        submit_button = WebDriverWait(driver, 50).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.btn.btn-primary'))
        )
        submit_button.click()

        save_all_button = WebDriverWait(driver, 50).until(
            EC.element_to_be_clickable((By.ID, 'btPdfDownload'))
        )
        save_all_button.click()

        download_button = WebDriverWait(driver, 100).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.btn.btn-outline-success'))
        )

        download_link = download_button.get_attribute('href')
        if not download_link:
            print(f"Could not find a download link for {link}")
            return

        download_pdf(download_link, save_folder, link)
    finally:
        driver.quit()


def _chunked(iterable: Iterable[str], chunk_size: int) -> Iterable[list[str]]:
    chunk: list[str] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def download_issuu_pdfs(links: Iterable[str], save_folder: str) -> None:
    print()
    print()
    print()
    print()
    print("Start downloading pdfs")

    max_processes = 20
    unique_links = list(dict.fromkeys(links))
    num_processes = min(multiprocessing.cpu_count(), max_processes)

    with multiprocessing.Pool(processes=num_processes) as pool:
        with tqdm(total=len(unique_links), desc="Downloading PDFs") as pbar:
            for chunk in _chunked(unique_links, num_processes):
                results = [pool.apply_async(download_link_pdf, args=(link, save_folder)) for link in chunk]
                for result in results:
                    result.get()
                    pbar.update(1)
    print("Finish downloading all the documents required")


def scrap_document_links(profile_url, save_folder):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    driver.get(profile_url)

    time.sleep(5)

    # Try to handle cookie consent if it appears
    try:
        allow_all_cookies_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, 'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll'))
        )
        allow_all_cookies_button.click()
        time.sleep(2)
        print("Cookie consent accepted")
    except:
        # Try alternative cookie button selectors
        try:
            # Try to find and click any "Allow all" or "Accept all" button
            cookie_buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'Allow') or contains(text(), 'Accept')]")
            if cookie_buttons:
                cookie_buttons[0].click()
                time.sleep(2)
                print("Cookie consent accepted (alternative method)")
        except:
            pass
        print("Continuing without cookie consent...")

    publication_links = []

    print("Begin scraping...")
    start_time = time.time()  # Record start time
    page_number = 1
    while True:
        print("=========================================================================")
        print("Scraping page number: " + str(page_number))

        publication_cards = driver.find_elements(By.CSS_SELECTOR, 'a[class*="PublicationCard__publication-card__card-link"]')

        for card in publication_cards:
            href = card.get_attribute('href')
            publication_links.append(href)
        print("Current number of files to download is: " + str(len(publication_links)))

        next_button = driver.find_elements(By.XPATH, f'//a[contains(@aria-label, "Page {page_number + 1}")]')

        if next_button:
            # move to next page - use JavaScript click to avoid interception
            try:
                driver.execute_script("arguments[0].click();", next_button[0])
            except:
                # Fallback to regular click
                next_button[0].click()
            page_number += 1
            time.sleep(5)
        else:
            print("Next link is disabled. End of pages.")
            break
      

    end_time = time.time()  # Record end time
    elapsed_time = end_time - start_time
    print(f"Scraping completed in {elapsed_time} seconds.")

    driver.quit()
    print("The Total number of links is: " + str(len(publication_links)))
    print("============================================================================")
    download_issuu_pdfs(publication_links, save_folder)


if __name__ == '__main__':
    profile_url = input("Please enter the profile URL: ")
    save_folder = input("Please enter the path to the save folder: ")
    scrap_document_links(profile_url, save_folder)
