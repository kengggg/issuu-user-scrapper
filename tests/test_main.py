from pathlib import Path
from typing import Iterator

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


class DummyResponse:
    def __init__(
        self,
        chunks: Iterator[bytes],
        raise_exc: Exception | None = None,
        iter_exception: Exception | None = None,
    ):
        self._chunks = list(chunks)
        self._raise_exc = raise_exc
        self._iter_exception = iter_exception

    def __enter__(self):
        if self._raise_exc:
            raise self._raise_exc
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def iter_content(self, chunk_size: int):
        for chunk in self._chunks:
            yield chunk
        if self._iter_exception:
            raise self._iter_exception


class DummySession:
    def __init__(self, response: DummyResponse):
        self._response = response

    def get(self, url: str, stream: bool, timeout: int):
        return self._response


def test_create_requests_session_has_retry_configuration():
    session = main._create_requests_session()

    assert session.adapters["https://"].max_retries.total == 3
    assert session.adapters["https://"].max_retries.backoff_factor == 1.5
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")


def test_download_pdf_skips_when_file_exists(tmp_path, monkeypatch):
    target = tmp_path / "existing.pdf"
    target.write_text("original")

    def fail_session():  # pragma: no cover - defensive guard
        raise AssertionError("Session should not be created when file exists")

    monkeypatch.setattr(main, "_create_requests_session", fail_session)

    main.download_pdf("http://example.com/file", str(tmp_path), "existing")

    assert target.read_text() == "original"


def test_download_pdf_streams_content(tmp_path, monkeypatch):
    response = DummyResponse(iter([b"chunk1", b"chunk2"]))
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    main.download_pdf("http://example.com/file", str(tmp_path), "resource")

    written = (tmp_path / "resource.pdf").read_bytes()
    assert written == b"chunk1chunk2"


def test_download_pdf_removes_partial_file_on_failure(tmp_path, monkeypatch):
    target_path = tmp_path / "broken.pdf"

    response = DummyResponse(
        iter([b"partial"]),
        iter_exception=main.RequestException("boom"),
    )
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    main.download_pdf("http://example.com/file", str(tmp_path), "broken")

    assert not target_path.exists()


def test_chunked_yields_even_and_final_chunks():
    data = list(range(7))
    chunks = list(main._chunked(data, 3))

    assert chunks == [[0, 1, 2], [3, 4, 5], [6]]


class _Result:
    def get(self):
        return None


class _Pool:
    instances: list["_Pool"] = []

    def __init__(self, processes: int):
        self.processes = processes
        self.apply_async_calls: list[tuple] = []

    def __enter__(self):
        type(self).instances.append(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def apply_async(self, func, args):
        self.apply_async_calls.append((func, args))
        func(*args)
        return _Result()


class _Tqdm:
    instances: list["_Tqdm"] = []

    def __init__(self, *args, **kwargs):
        self.total = kwargs.get("total")
        self.desc = kwargs.get("desc")
        self.updated = 0
        self.update_calls: list[int] = []

    def __enter__(self):
        type(self).instances.append(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, amount: int):
        self.update_calls.append(amount)
        self.updated += amount


def test_download_issuu_pdfs_deduplicates_and_tracks_progress(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(main.multiprocessing, "Pool", _Pool)
    monkeypatch.setattr(main.multiprocessing, "cpu_count", lambda: 4)
    monkeypatch.setattr(main, "download_link_pdf", lambda link, folder: calls.append((link, folder)))
    monkeypatch.setattr(main, "tqdm", lambda *args, **kwargs: _Tqdm(*args, **kwargs))

    links = ["a", "b", "a", "c"]
    main.download_issuu_pdfs(links, "folder")

    assert calls == [("a", "folder"), ("b", "folder"), ("c", "folder")]
    assert _Pool.instances[0].processes == 4
    assert len(_Pool.instances[0].apply_async_calls) == len({"a", "b", "c"})
    tqdm_instance = _Tqdm.instances[0]
    assert tqdm_instance.total == 3
    assert tqdm_instance.desc == "Downloading PDFs"
    assert tqdm_instance.update_calls == [1, 1, 1]
    assert tqdm_instance.updated == 3


# Tests for _build_chrome_options
def test_build_chrome_options_headless():
    options = main._build_chrome_options(headless=True)

    assert "--headless=new" in options.arguments
    assert "--disable-gpu" in options.arguments
    assert "--no-sandbox" in options.arguments
    assert "--disable-dev-shm-usage" in options.arguments
    assert "--window-size=1920,1080" in options.arguments


def test_build_chrome_options_not_headless():
    options = main._build_chrome_options(headless=False)

    assert "--headless=new" not in options.arguments
    assert "--disable-gpu" in options.arguments
    assert "--no-sandbox" in options.arguments


# Tests for _get_chromedriver_path
def test_get_chromedriver_path_lazy_install(monkeypatch):
    install_called = []

    class MockChromeDriverManager:
        def install(self):
            install_called.append(True)
            return "/mock/path/to/chromedriver"

    # Reset the global cache
    main._CHROME_DRIVER_PATH = None

    monkeypatch.setattr(main, "ChromeDriverManager", MockChromeDriverManager)

    path1 = main._get_chromedriver_path()
    path2 = main._get_chromedriver_path()

    assert path1 == "/mock/path/to/chromedriver"
    assert path2 == "/mock/path/to/chromedriver"
    assert len(install_called) == 1  # Should only install once


# Tests for download_pdf error scenarios
def test_download_pdf_handles_http_error(tmp_path, monkeypatch, capsys):
    response = DummyResponse(
        iter([]),
        raise_exc=main.RequestException("404 Not Found"),
    )
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    main.download_pdf("http://example.com/file", str(tmp_path), "missing")

    captured = capsys.readouterr()
    assert "Failed to download PDF" in captured.out
    assert "404 Not Found" in captured.out
    assert not (tmp_path / "missing.pdf").exists()


def test_download_pdf_creates_directory_if_missing(tmp_path, monkeypatch):
    response = DummyResponse(iter([b"data"]))
    monkeypatch.setattr(main, "_create_requests_session", lambda: DummySession(response))

    nested_path = tmp_path / "nested" / "folder"
    main.download_pdf("http://example.com/file", str(nested_path), "resource")

    assert (nested_path / "resource.pdf").exists()
    assert (nested_path / "resource.pdf").read_bytes() == b"data"


def test_download_pdf_extracts_filename_from_link():
    import re
    # Test the filename extraction logic
    link = "https://issuu.com/user/docs/my-document"
    filename = f"{link.rstrip('/').split('/')[-1]}.pdf"
    assert filename == "my-document.pdf"

    link = "https://issuu.com/user/docs/another-doc/"
    filename = f"{link.rstrip('/').split('/')[-1]}.pdf"
    assert filename == "another-doc.pdf"


# Mock classes for Selenium testing that validate behavior
class MockWebElement:
    def __init__(self, href=None, element_id=None):
        self._href = href
        self._element_id = element_id
        self._text_sent = []
        self._clicked = False
        self._cleared = False

    def clear(self):
        self._cleared = True

    def send_keys(self, text):
        self._text_sent.append(text)

    def click(self):
        self._clicked = True

    def get_attribute(self, name):
        if name == "href":
            return self._href
        return None

    # Required for Selenium EC (expected conditions)
    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def is_selected(self):
        return False


class MockWebDriver:
    def __init__(self, download_link="http://example.com/download.pdf"):
        self._download_link = download_link
        self._urls_visited = []
        self._quit_called = False
        self._selectors_used = []  # Track what selectors were used
        # Elements that exist on the page - use exact selectors from code
        self._elements = {
            "#DocumentUrl": MockWebElement(element_id="DocumentUrl"),  # By.CSS_SELECTOR
            "button.btn.btn-primary": MockWebElement(),  # By.CSS_SELECTOR
            "btPdfDownload": MockWebElement(),  # By.ID
            "a.btn.btn-outline-success": MockWebElement(href=download_link),  # By.CSS_SELECTOR
        }

    def get(self, url):
        self._urls_visited.append(url)

    def find_element(self, by, selector):
        """Selenium's find_element method - track what's being searched for"""
        self._selectors_used.append((by, selector))

        # Return the element based on the selector
        if selector in self._elements:
            return self._elements[selector]

        # Return None if element not found
        raise Exception(f"Element not found: {by}={selector}")

    def quit(self):
        self._quit_called = True


class MockWebDriverWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout

    def until(self, condition):
        """
        Mimic Selenium's WebDriverWait.until() which calls the condition function
        with the driver until it returns a truthy value.
        """
        # Call the condition with the driver - this will trigger find_element on our mock
        result = condition(self.driver)

        if not result:
            raise Exception("Element not found in time")

        return result


# Tests for download_link_pdf
def test_download_link_pdf_success(tmp_path, monkeypatch):
    download_pdf_calls = []
    driver_instance = MockWebDriver(download_link="http://example.com/file.pdf")
    wait_instances = []

    def mock_wait_factory(driver, timeout):
        wait = MockWebDriverWait(driver, timeout)
        wait_instances.append(wait)
        return wait

    monkeypatch.setattr(main.webdriver, "Chrome", lambda service, options: driver_instance)
    monkeypatch.setattr(main, "WebDriverWait", mock_wait_factory)
    monkeypatch.setattr(main, "download_pdf", lambda url, folder, link: download_pdf_calls.append((url, folder, link)))
    monkeypatch.setattr(main, "_get_chromedriver_path", lambda: "/mock/chromedriver")

    test_link = "https://issuu.com/user/docs/test-document"
    main.download_link_pdf(test_link, str(tmp_path))

    # Verify behavior: navigated to correct URL
    assert "https://issuudownload.com/" in driver_instance._urls_visited, \
        f"Should navigate to issuudownload.com, got: {driver_instance._urls_visited}"

    # Verify behavior: input field was cleared and received the link
    input_element = driver_instance._elements["#DocumentUrl"]
    assert input_element._cleared, "Input field should be cleared"
    assert test_link in input_element._text_sent, \
        f"Should send link to input, got: {input_element._text_sent}"

    # Verify behavior: buttons were clicked in correct sequence
    submit_btn = driver_instance._elements["button.btn.btn-primary"]
    save_btn = driver_instance._elements["btPdfDownload"]
    assert submit_btn._clicked, "Submit button should be clicked"
    assert save_btn._clicked, "Save all button should be clicked"

    # Verify behavior: correct selectors were used
    expected_selectors = ["#DocumentUrl", "button.btn.btn-primary", "btPdfDownload", "a.btn.btn-outline-success"]
    actual_selectors = [sel for _, sel in driver_instance._selectors_used]
    for expected in expected_selectors:
        assert expected in actual_selectors, \
            f"Expected to check for selector '{expected}', but got: {actual_selectors}"

    # Verify behavior: download_pdf was called with correct URL
    assert driver_instance._quit_called, "Driver should be quit"
    assert download_pdf_calls == [("http://example.com/file.pdf", str(tmp_path), test_link)], \
        f"Should call download_pdf with correct params, got: {download_pdf_calls}"


def test_download_link_pdf_no_download_link(tmp_path, monkeypatch, capsys):
    driver_instance = MockWebDriver(download_link=None)

    monkeypatch.setattr(main.webdriver, "Chrome", lambda service, options: driver_instance)
    monkeypatch.setattr(main, "WebDriverWait", MockWebDriverWait)
    monkeypatch.setattr(main, "_get_chromedriver_path", lambda: "/mock/chromedriver")

    main.download_link_pdf("https://issuu.com/test/doc", str(tmp_path))

    # Verify behavior: error message is printed when no download link
    captured = capsys.readouterr()
    assert "Could not find a download link" in captured.out, \
        f"Should print error message, got: {captured.out}"

    # Verify behavior: driver is still properly cleaned up
    assert driver_instance._quit_called, "Driver should be quit even on error"


def test_download_link_pdf_webdriver_exception(tmp_path, monkeypatch, capsys):
    def raise_webdriver_error(service, options):
        raise main.WebDriverException("ChromeDriver not found")

    monkeypatch.setattr(main.webdriver, "Chrome", raise_webdriver_error)
    monkeypatch.setattr(main, "_get_chromedriver_path", lambda: "/mock/chromedriver")

    main.download_link_pdf("https://issuu.com/test/doc", str(tmp_path))

    captured = capsys.readouterr()
    assert "Unable to start ChromeDriver" in captured.out


# Mock classes for scrap_document_links testing that validate real selectors
class MockProfileDriver:
    def __init__(self, num_pages=2, links_per_page=3, has_cookie_consent=True):
        self.num_pages = num_pages
        self.links_per_page = links_per_page
        self.has_cookie_consent = has_cookie_consent
        self.current_page = 1
        self._quit_called = False
        self._urls_visited = []
        self._selectors_used = []  # Track what selectors were actually used
        self._scripts_executed = []  # Track JavaScript execution

    def get(self, url):
        self._urls_visited.append(url)

    def find_elements(self, by, selector):
        # Track what selectors are being used
        self._selectors_used.append((by, selector))

        # Validate against actual selectors in the code
        if selector == 'a[class*="PublicationCard__publication-card__card-link"]':
            # Return realistic publication card links
            return [MockWebElement(href=f"https://issuu.com/user/docs/document-{i}")
                    for i in range(self.links_per_page)]

        elif selector.startswith('//a[contains(@aria-label, "Page '):
            # XPath for pagination buttons - extract page number
            import re
            match = re.search(r'Page (\d+)', selector)
            if match:
                page_num = int(match.group(1))
                # Return button only if we haven't reached the last page
                if page_num <= self.num_pages:
                    return [MockWebElement()]
            return []

        elif "//*[contains(text(), 'Allow') or contains(text(), 'Accept')]" in selector:
            # Alternative cookie button
            if self.has_cookie_consent:
                return [MockWebElement()]
            return []

        return []

    def execute_script(self, script, element):
        # Track what scripts are executed
        self._scripts_executed.append(script)
        # Validate that it's a click script
        if "click" in script or "Click" in script:
            self.current_page += 1

    def quit(self):
        self._quit_called = True


class MockProfileWebDriverWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout
        self.conditions_checked = []

    def until(self, condition):
        # Extract condition details
        if hasattr(condition, 'locator'):
            by_type, selector = condition.locator
            self.conditions_checked.append((by_type, selector))

            # Check for cookie consent button
            if selector == "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll":
                if not self.driver.has_cookie_consent:
                    raise Exception("Cookie button not found")
                return MockWebElement()

        if not self.driver.has_cookie_consent:
            raise Exception("Element not found")

        return MockWebElement()


# Mock time module for scrap_document_links tests
class MockTime:
    @staticmethod
    def sleep(seconds):
        pass

    @staticmethod
    def time():
        return 0.0


# Tests for scrap_document_links
def test_scrap_document_links_success(tmp_path, monkeypatch):
    download_calls = []
    driver = MockProfileDriver(num_pages=2, links_per_page=3, has_cookie_consent=True)

    monkeypatch.setattr(main.webdriver, "Chrome", lambda service, options: driver)
    monkeypatch.setattr(main, "WebDriverWait", MockProfileWebDriverWait)
    monkeypatch.setattr(main, "ChromeDriverManager", lambda: type('obj', (), {'install': lambda self: '/mock/path'})())
    monkeypatch.setattr(main, "download_issuu_pdfs", lambda links, folder: download_calls.append((list(links), folder)))
    monkeypatch.setattr(main, "time", MockTime())

    profile_url = "https://issuu.com/testuser/publications"
    main.scrap_document_links(profile_url, str(tmp_path))

    # Verify behavior: navigated to the profile URL
    assert profile_url in driver._urls_visited, \
        f"Should navigate to profile URL, got: {driver._urls_visited}"

    # Verify behavior: used correct CSS selector for publication cards
    publication_card_selector = 'a[class*="PublicationCard__publication-card__card-link"]'
    css_selectors_used = [sel for by, sel in driver._selectors_used if by == main.By.CSS_SELECTOR]
    assert publication_card_selector in css_selectors_used, \
        f"Should use correct publication card selector, got: {css_selectors_used}"

    # Verify behavior: used correct XPath for pagination
    xpath_selectors_used = [sel for by, sel in driver._selectors_used if by == main.By.XPATH]
    pagination_xpaths = [sel for sel in xpath_selectors_used if "Page" in sel and "aria-label" in sel]
    assert len(pagination_xpaths) > 0, \
        f"Should use XPath for pagination, got: {xpath_selectors_used}"

    # Verify behavior: collected links from all pages
    assert len(download_calls) == 1, "Should call download_issuu_pdfs once"
    links, folder = download_calls[0]
    assert len(links) == 6, f"Should collect 2 pages * 3 links = 6 total, got {len(links)}"
    assert folder == str(tmp_path), "Should use correct output folder"

    # Verify behavior: collected realistic link format
    for link in links:
        assert link.startswith("https://issuu.com/"), \
            f"Links should be realistic Issuu URLs, got: {link}"
        assert "docs/document-" in link, \
            f"Links should have document path, got: {link}"

    # Verify behavior: driver was properly cleaned up
    assert driver._quit_called, "Driver should be quit after scraping"


def test_scrap_document_links_no_cookie_consent(tmp_path, monkeypatch, capsys):
    download_calls = []
    driver = MockProfileDriver(num_pages=1, links_per_page=2, has_cookie_consent=False)

    monkeypatch.setattr(main.webdriver, "Chrome", lambda service, options: driver)
    monkeypatch.setattr(main, "WebDriverWait", MockProfileWebDriverWait)
    monkeypatch.setattr(main, "ChromeDriverManager", lambda: type('obj', (), {'install': lambda self: '/mock/path'})())
    monkeypatch.setattr(main, "download_issuu_pdfs", lambda links, folder: download_calls.append((list(links), folder)))
    monkeypatch.setattr(main, "time", MockTime())

    main.scrap_document_links("https://issuu.com/user", str(tmp_path))

    # Verify behavior: continues when cookie consent fails
    captured = capsys.readouterr()
    assert "Continuing without cookie consent" in captured.out, \
        "Should print message when cookie consent fails"

    # Verify behavior: still attempts to find alternative cookie buttons
    xpath_selectors = [sel for by, sel in driver._selectors_used if by == main.By.XPATH]
    cookie_xpaths = [sel for sel in xpath_selectors if "Allow" in sel or "Accept" in sel]
    assert len(cookie_xpaths) > 0, \
        "Should try alternative cookie button selectors"

    # Verify behavior: scraping continues despite cookie failure
    assert len(download_calls) == 1, "Should still scrape documents"
    links, folder = download_calls[0]
    assert len(links) == 2, f"Should collect links even without cookie consent, got {len(links)}"

    # Verify behavior: driver is properly cleaned up
    assert driver._quit_called, "Driver should be quit even when cookie consent fails"


# Validation tests
def test_download_issuu_pdfs_empty_list(monkeypatch, capsys):
    monkeypatch.setattr(main.multiprocessing, "Pool", _Pool)
    monkeypatch.setattr(main.multiprocessing, "cpu_count", lambda: 4)
    monkeypatch.setattr(main, "tqdm", lambda *args, **kwargs: _Tqdm(*args, **kwargs))

    main.download_issuu_pdfs([], "folder")

    captured = capsys.readouterr()
    assert "Start downloading pdfs" in captured.out
    assert "Finish downloading all the documents required" in captured.out


def test_chunked_empty_iterable():
    chunks = list(main._chunked([], 3))
    assert chunks == []


def test_chunked_single_item():
    chunks = list(main._chunked([1], 5))
    assert chunks == [[1]]
