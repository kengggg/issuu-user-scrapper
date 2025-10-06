# CLAUDE.md - Development Documentation

## Project Overview

**issuu-user-scrapper** is a Python-based web scraper that downloads PDF documents from Issuu user profiles. It uses Selenium WebDriver to navigate profile pages, extract publication links, and downloads them via a third-party conversion service.

### Tech Stack
- **Language:** Python 3.12+
- **Web Scraping:** Selenium WebDriver (Chrome)
- **HTTP Requests:** requests library with retry logic
- **Concurrency:** multiprocessing.Pool
- **Testing:** pytest with coverage

---

## Architecture

### Core Components

#### 1. **Profile Scraper** (`scrap_document_links`)
- Navigates to Issuu user profile pages
- Handles cookie consent dialogs (with fallback)
- Extracts publication links using CSS selectors
- Supports pagination across multiple pages
- Uses XPath to detect and click "Next Page" buttons

**Key Selectors:**
```python
# Publication cards
'a[class*="PublicationCard__publication-card__card-link"]'

# Pagination
'//a[contains(@aria-label, "Page {page_number}")]'

# Cookie consent
'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll'  # Primary
"//*[contains(text(), 'Allow') or contains(text(), 'Accept')]"  # Fallback
```

#### 2. **PDF Downloader** (`download_link_pdf`)
- Automates interaction with issuudownload.com
- Navigates through conversion workflow:
  1. Enter Issuu URL
  2. Click submit button
  3. Click "Save All" to generate PDF
  4. Extract download link
  5. Download PDF file

**Workflow Selectors:**
```python
'#DocumentUrl'                    # Input field (CSS)
'button.btn.btn-primary'          # Submit button (CSS)
'btPdfDownload'                   # Save All button (ID)
'a.btn.btn-outline-success'       # Download link (CSS)
```

#### 3. **HTTP Download** (`download_pdf`)
- Streams PDF files to disk with chunking (8KB chunks)
- Skips existing files to avoid re-downloads
- Implements retry logic (3 attempts with exponential backoff)
- Cleans up partial files on failure
- Creates directory structure automatically

#### 4. **Parallel Processing** (`download_issuu_pdfs`)
- Deduplicates link list before processing
- Adapts pool size to CPU count (max 20 processes)
- Chunks work distribution for progress tracking
- Uses tqdm for visual progress bars

---

## Code Organization

```
issuu-user-scrapper/
├── main.py                 # Main script with all functionality
├── tests/
│   └── test_main.py       # Comprehensive test suite (94% coverage)
├── requirements.txt        # Python dependencies
├── .gitignore             # Git exclusions
└── CLAUDE.md              # This file
```

### Key Functions

| Function | Purpose | Lines |
|----------|---------|-------|
| `scrap_document_links()` | Main entry point - scrapes profile | 171-242 |
| `download_issuu_pdfs()` | Parallel download orchestrator | 150-168 |
| `download_link_pdf()` | Selenium-based PDF converter | 96-136 |
| `download_pdf()` | HTTP streaming downloader | 45-71 |
| `_create_requests_session()` | Configure HTTP retry logic | 24-42 |
| `_build_chrome_options()` | Configure Chrome headless mode | 73-81 |
| `_get_chromedriver_path()` | Lazy ChromeDriver installation | 87-93 |
| `_chunked()` | Chunk iterator for batching | 139-147 |

---

## Testing Strategy

### Test Philosophy

Tests are designed to **validate behavior**, not just code execution. Mocks simulate realistic Selenium interactions and validate:
- Correct selectors are used
- Elements are interacted with properly
- Error handling works correctly
- Data formats match real-world scenarios

### Test Coverage: 94%

**Covered Components:**
- ✅ HTTP session configuration (retry, backoff, user-agent)
- ✅ PDF download with streaming and cleanup
- ✅ Directory creation and file existence checks
- ✅ Chrome options (headless/non-headless)
- ✅ ChromeDriver lazy loading and caching
- ✅ Selenium workflow for PDF conversion
- ✅ Profile scraping with pagination
- ✅ Cookie consent handling (success and failure paths)
- ✅ Empty input validation
- ✅ Chunking logic edge cases

**Not Covered (10 lines):**
- Deep exception handler branches (lines 196-200, 225-227)
- `if __name__ == '__main__'` block (lines 246-248)

### Mock Architecture

#### MockWebElement
```python
class MockWebElement:
    # Tracks state changes
    _cleared: bool          # Was clear() called?
    _clicked: bool          # Was click() called?
    _text_sent: list[str]   # What text was sent via send_keys()?

    # Selenium compatibility
    is_displayed() -> bool
    is_enabled() -> bool
```

#### MockWebDriver
```python
class MockWebDriver:
    # Behavior tracking
    _urls_visited: list[str]        # Navigation history
    _selectors_used: list[tuple]    # (By type, selector) pairs

    # Element registry
    _elements: dict[str, MockWebElement]  # Selector -> Element mapping

    # Implements real Selenium API
    find_element(by, selector) -> MockWebElement
```

#### MockWebDriverWait
```python
class MockWebDriverWait:
    # Uses REAL Selenium expected_conditions
    def until(self, condition):
        # Calls EC.element_to_be_clickable() etc.
        return condition(self.driver)
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ -v --cov=main --cov-report=term-missing

# Run specific test
python -m pytest tests/test_main.py::test_download_link_pdf_success -v

# Run with detailed output
python -m pytest tests/ -vv --tb=long
```

---

## Configuration & Environment

### Dependencies

```txt
requests>=2.31.0          # HTTP library
selenium>=4.15.0          # Web automation
webdriver-manager>=4.0.1  # Auto ChromeDriver installation
tqdm>=4.66.0             # Progress bars
pytest>=8.3.2            # Testing framework
pytest-cov>=5.0.0        # Coverage reporting
```

### Chrome Options

**Headless Mode (Production):**
```python
--headless=new           # Modern headless mode
--disable-gpu           # Disable GPU acceleration
--no-sandbox            # Required for some environments
--disable-dev-shm-usage # Overcome limited resource problems
--window-size=1920,1080 # Set viewport size
```

### HTTP Session Configuration

```python
Retry Strategy:
- Total retries: 3
- Backoff factor: 1.5 (1.5s, 3s, 6s)
- Status codes: 429, 500, 502, 503, 504
- Methods: GET only
- Timeout: 30 seconds
```

### Multiprocessing

```python
Pool Size = min(cpu_count(), 20)
Chunk Size = pool_size  # For progress tracking
```

---

## Common Tasks

### Adding a New Test

1. **Identify behavior to test**
   ```python
   # What should the code DO, not just execute?
   # Example: "Should navigate to the correct URL"
   ```

2. **Create realistic mocks**
   ```python
   # Use exact selectors from main.py
   # Track operations, don't fake results
   driver = MockWebDriver()
   driver._urls_visited  # Will be populated by code
   ```

3. **Assert behavior, not just success**
   ```python
   # ❌ Bad: assert result is not None
   # ✅ Good: assert "https://issuudownload.com/" in driver._urls_visited
   ```

4. **Use descriptive assertion messages**
   ```python
   assert condition, f"Expected X but got {actual_value}"
   ```

### Debugging Selenium Issues

1. **Run in non-headless mode**
   ```python
   chrome_options = _build_chrome_options(headless=False)
   ```

2. **Add wait times**
   ```python
   time.sleep(5)  # After navigation
   ```

3. **Check selector validity**
   - Open browser DevTools (F12)
   - Test CSS selector: `$('a[class*="PublicationCard"]')`
   - Test XPath: `$x('//a[contains(@aria-label, "Page 2")]')`

4. **Capture screenshots**
   ```python
   driver.save_screenshot('debug.png')
   ```

### Updating Selectors

If Issuu changes their HTML structure:

1. **Identify broken selector**
   ```bash
   # Test will fail with "Element not found"
   python -m pytest tests/test_main.py::test_scrap_document_links_success -v
   ```

2. **Update in main.py**
   ```python
   # Find the CSS_SELECTOR or XPATH
   publication_cards = driver.find_elements(
       By.CSS_SELECTOR,
       'a[class*="NewClassName"]'  # Update here
   )
   ```

3. **Update in test_main.py**
   ```python
   class MockProfileDriver:
       def find_elements(self, by, selector):
           if selector == 'a[class*="NewClassName"]':  # Update here too
               return [MockWebElement(...)]
   ```

4. **Verify tests pass**
   ```bash
   python -m pytest tests/ -v
   ```

---

## Error Handling

### HTTP Errors
```python
try:
    response.raise_for_status()
except RequestException as exc:
    # Cleanup partial files
    if filepath.exists():
        filepath.unlink()
    print(f"Failed to download PDF from {url}: {exc}")
```

### Selenium Errors
```python
try:
    driver = webdriver.Chrome(...)
except WebDriverException as exc:
    print(f"Unable to start ChromeDriver: {exc}")
    return  # Graceful degradation
```

### Cookie Consent Failures
```python
try:
    # Primary method
    cookie_button.click()
except:
    try:
        # Fallback method
        alternative_buttons = driver.find_elements(...)
        if alternative_buttons:
            alternative_buttons[0].click()
    except:
        print("Continuing without cookie consent...")
        # Script continues - cookies not critical
```

---

## Performance Considerations

### Bottlenecks

1. **Network I/O** - Downloading large PDFs
   - Mitigation: Parallel processing with multiprocessing
   - Chunk size: 8KB for memory efficiency

2. **Selenium Wait Times** - WebDriverWait timeouts
   - Input field: 50s
   - Submit button: 50s
   - Save button: 50s
   - Download link: 100s (PDF generation takes time)

3. **Page Navigation** - Sleep delays
   - After navigation: 5s
   - After cookie consent: 2s
   - After pagination click: 5s

### Optimization Opportunities

1. **Reduce sleep times** - Use explicit waits instead
2. **Increase pool size** - Currently capped at 20
3. **Cache ChromeDriver** - Already implemented (lazy loading)
4. **Skip file existence checks** - Already implemented

---

## Maintenance & Best Practices

### Code Style

- **Functions:** Snake_case, descriptive names
- **Private functions:** Prefix with `_`
- **Constants:** UPPER_CASE (e.g., `_CHROME_DRIVER_PATH`)
- **Type hints:** Use where helpful (PEP 484)
- **Docstrings:** Required for public functions

### Git Workflow

```bash
# Typical development cycle
git add .
git commit -m "feat: add pagination support"
git push origin main
```

### Updating Dependencies

```bash
# Update all packages
pip install --upgrade -r requirements.txt

# Update specific package
pip install --upgrade selenium

# Regenerate requirements
pip freeze > requirements.txt
```

### Adding New Features

1. Write tests first (TDD approach)
2. Implement functionality in main.py
3. Ensure tests pass (94%+ coverage)
4. Update this documentation
5. Commit with descriptive message

---

## Troubleshooting

### ChromeDriver Issues

**Problem:** `Unable to start ChromeDriver`

**Solutions:**
1. Delete cached driver: `rm -rf ~/.wdm`
2. Update webdriver-manager: `pip install --upgrade webdriver-manager`
3. Check Chrome version: `google-chrome --version`

### Cookie Consent Blocking

**Problem:** Script fails on cookie dialog

**Solution:**
- Cookie handling has fallbacks - should auto-continue
- If persistent, manually inspect page and update selectors
- Can disable in test: `has_cookie_consent=False`

### Download Failures

**Problem:** PDFs not downloading

**Solutions:**
1. Check issuudownload.com is accessible
2. Verify selectors haven't changed
3. Increase wait times (timeouts)
4. Check disk space

### Test Failures

**Problem:** Tests fail after code changes

**Solutions:**
1. Run single test: `pytest tests/test_main.py::test_name -v`
2. Check assertion messages for details
3. Verify mocks match actual selectors
4. Update mock behavior to match code changes

---

## Future Enhancements

### Potential Improvements

1. **Better Error Recovery**
   - Retry failed downloads
   - Resume interrupted scraping sessions
   - Save progress to disk

2. **Configuration File**
   - YAML/JSON config for selectors
   - Customizable wait times
   - User-defined pool size

3. **Logging System**
   - Replace print() with logging module
   - Different log levels (DEBUG, INFO, ERROR)
   - Log file rotation

4. **Alternative Download Methods**
   - Direct Issuu API (if available)
   - Multiple conversion services
   - Fallback strategies

5. **UI Improvements**
   - CLI with argparse
   - Interactive mode
   - Better progress reporting

6. **Data Validation**
   - Verify PDF integrity
   - Check file sizes
   - Metadata extraction

---

## Changelog

### Recent Improvements (Current Session)

**Test Suite Enhancement (2025-01-06)**
- ✅ Added 14 new tests (from 6 to 20 tests)
- ✅ Increased coverage from ~40% to 94%
- ✅ Rewrote mocks to validate behavior, not just execution
- ✅ Added comprehensive assertions with error messages
- ✅ Mocks now use real Selenium API (EC conditions)
- ✅ Tests validate actual selectors and interactions

**Key Changes:**
- MockWebDriverWait now calls real `expected_conditions` functions
- MockWebDriver implements `find_element()` API
- MockWebElement tracks state changes (`_cleared`, `_clicked`, `_text_sent`)
- Tests assert realistic data formats (Issuu URLs, document paths)
- Added tests for edge cases (empty inputs, errors, cookie failures)

---

## Contact & Support

### Resources

- **Selenium Docs:** https://selenium-python.readthedocs.io/
- **pytest Docs:** https://docs.pytest.org/
- **Issuu:** https://issuu.com/

### Getting Help

1. Check test failures for specific error messages
2. Review this documentation for common issues
3. Search GitHub issues for similar problems
4. Create detailed bug report with:
   - Python version
   - Chrome version
   - Error stacktrace
   - Steps to reproduce

---

## License & Legal

**Disclaimer:** This tool is for educational purposes. Ensure compliance with:
- Issuu's Terms of Service
- Copyright laws
- Rate limiting and respectful scraping practices

**Usage Guidelines:**
- Don't overload servers (respect rate limits)
- Only download content you have rights to
- Use for personal/research purposes only
- Attribute content to original creators

---

*Last Updated: 2025-01-06*
*Coverage: 94% | Tests: 20/20 Passing*
