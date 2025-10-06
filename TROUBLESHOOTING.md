# Troubleshooting Guide

## Rust Version Errors

### 1. "Connection refused (os error 61)"

**Problem:** ChromeDriver is not running

**Solution:**
```bash
# Check if ChromeDriver is running
lsof -ti:9515

# If not running, start it:
cd rust
./start-chromedriver.sh

# Or manually:
chromedriver --port=9515 &
```

**Verify it's working:**
```bash
curl http://localhost:9515/status
# Should return JSON with "ready": true
```

---

### 2. "element not interactable"

**Problem:** Issuu website selectors have changed OR timing issues

**Diagnosis:**
```bash
# The error occurred at this selector (check ChromeDriver logs):
# /tmp/chromedriver.log
```

**Quick Fix - Use Python Version:**
```bash
# The Python version is more stable and handles selector changes better
cd python
python main.py
# Enter URL: https://issuu.com/bangkokpatana
# Enter folder: /Users/keng/Downloads
```

**Rust Fix Options:**

**Option 1: Update wait times (if timing issue)**
Edit `rust/src/lib.rs` and increase timeout values:
```rust
// Line ~111: Change from 50 to 100 seconds
.wait(Duration::from_secs(100), Duration::from_millis(500))
```

**Option 2: Run in visible mode (for debugging)**
Edit `rust/src/lib.rs`:
```rust
// Line ~81: Change headless parameter
pub async fn build_chrome_capabilities(headless: bool) -> Result<WebDriver> {
    // ...
    if headless {  // Change to: if false {
```

Then rebuild:
```bash
cd rust
cargo build --release
```

**Option 3: Check if selectors changed**
The current selectors are:
- Input field: `#DocumentUrl`
- Submit button: `button.btn.btn-primary`
- Save button: `btPdfDownload`
- Download link: `a.btn.btn-outline-success`

Visit https://issuudownload.com/ in your browser and check if these still exist.

---

### 3. "ChromeDriver not found"

**Problem:** ChromeDriver not installed

**macOS Solution:**
```bash
brew install --cask chromedriver
xattr -d com.apple.quarantine /opt/homebrew/bin/chromedriver
```

**Linux Solution:**
```bash
sudo apt-get install chromium-chromedriver
```

**Manual Install:**
```bash
# Download from: https://chromedriver.chromium.org/downloads
# Move to PATH:
sudo mv chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver
```

---

### 4. Chrome Version Mismatch

**Error:** "This version of ChromeDriver only supports Chrome version X"

**Check versions:**
```bash
# Chrome version
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version

# ChromeDriver version
chromedriver --version
```

**Update ChromeDriver:**
```bash
brew upgrade --cask chromedriver
```

---

## Python Version Errors

### ChromeDriver Issues

**Error:** `Unable to start ChromeDriver`

**Solution:**
```bash
# Python auto-installs ChromeDriver, but if it fails:
pip install --upgrade webdriver-manager

# Clear cache
rm -rf ~/.wdm
```

### Import Errors

**Error:** `No module named 'selenium'`

**Solution:**
```bash
cd python
pip install -r requirements.txt
```

---

## General Issues

### Port Already in Use

**Error:** `Address already in use (48)` or `Port 9515 already bound`

**Find what's using the port:**
```bash
lsof -ti:9515
```

**Kill the process:**
```bash
kill $(lsof -ti:9515)
```

**Or use a different port:**
Edit `rust/src/lib.rs` and change:
```rust
WebDriver::new("http://localhost:9515", caps)  // Change 9515 to 9516
```

---

### Network/Download Issues

**Slow downloads:**
- Check internet connection
- Issuu server might be slow
- Try reducing parallel downloads in code

**Failed downloads:**
- File might not exist on Issuu
- PDF might be restricted
- Check console output for specific errors

---

## Recommended Workflow

**For Production Use:**
```bash
# Use Python version (more stable)
cd python
python main.py
```

**For Development/Testing:**
```bash
# Use Rust version (faster)
cd rust
./start-chromedriver.sh
./target/release/issuu_scraper -p <url> -s <folder>
./stop-chromedriver.sh
```

---

## Quick Commands Reference

```bash
# Check ChromeDriver status
curl http://localhost:9515/status

# Start ChromeDriver
chromedriver --port=9515 &

# Stop ChromeDriver
kill $(lsof -ti:9515)

# Python quick run
cd python && python main.py

# Rust quick run
cd rust && ./target/release/issuu_scraper -p <url> -s <folder>

# Run tests
cd python && pytest tests/ -v          # Python
cd rust && cargo test                  # Rust

# View logs
tail -f /tmp/chromedriver.log          # ChromeDriver logs
```

---

## Getting Help

1. **Check ChromeDriver logs:** `/tmp/chromedriver.log`
2. **Check browser DevTools:** Inspect the Issuu page for selector changes
3. **Try Python version:** More stable with auto-retry
4. **GitHub Issues:** https://github.com/poysa213/issuu-user-scrapper/issues

---

## Current Known Issues

1. **Rust "element not interactable"** - Issuu website may have changed selectors
   - **Workaround:** Use Python version
   - **Fix:** Update selectors in `rust/src/lib.rs`

2. **macOS ChromeDriver security** - Requires removing quarantine
   - **Fix:** `xattr -d com.apple.quarantine /opt/homebrew/bin/chromedriver`

3. **Chrome version mismatch** - ChromeDriver must match Chrome version
   - **Fix:** `brew upgrade --cask chromedriver`
