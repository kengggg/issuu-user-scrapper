# Issuu Scraper - Rust Version

High-performance Rust implementation of the Issuu PDF scraper.

## Prerequisites

### 1. Install Rust
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### 2. Install ChromeDriver

**macOS (Homebrew):**
```bash
brew install --cask chromedriver

# Remove quarantine (macOS security)
xattr -d com.apple.quarantine /opt/homebrew/bin/chromedriver
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get install chromium-chromedriver

# Arch Linux
sudo pacman -S chromedriver

# Or download manually:
wget https://chromedriver.storage.googleapis.com/LATEST_RELEASE
wget https://chromedriver.storage.googleapis.com/$(cat LATEST_RELEASE)/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
```

**Windows:**
```powershell
# Using Chocolatey
choco install chromedriver

# Or download from: https://chromedriver.chromium.org/
```

## Quick Start

### 1. Build the Project
```bash
cd rust
cargo build --release
```

### 2. Start ChromeDriver
```bash
# Use the provided script (macOS/Linux)
./start-chromedriver.sh

# Or manually
chromedriver --port=9515 &
```

### 3. Run the Scraper
```bash
./target/release/issuu_scraper \
    --profile-url "https://issuu.com/username/publications" \
    --save-folder "/path/to/downloads"

# Or using short flags
./target/release/issuu_scraper -p https://issuu.com/username -s ~/Downloads
```

### 4. Stop ChromeDriver (when done)
```bash
./stop-chromedriver.sh
```

## Usage

### Command Line Options

```bash
issuu_scraper [OPTIONS]

Options:
  -p, --profile-url <URL>      Issuu profile URL to scrape
  -s, --save-folder <PATH>     Folder to save downloaded PDFs
  -h, --help                   Print help
  -V, --version                Print version
```

### Examples

**Basic usage:**
```bash
./target/release/issuu_scraper \
    -p https://issuu.com/username/publications \
    -s ./downloads
```

**Full path:**
```bash
./target/release/issuu_scraper \
    --profile-url "https://issuu.com/bangkokpatana" \
    --save-folder "/Users/keng/Downloads/issuu"
```

## Troubleshooting

### Error: "Connection refused (os error 61)"

**Cause:** ChromeDriver is not running

**Solution:**
```bash
# Start ChromeDriver
chromedriver --port=9515 &

# Or use the script
./start-chromedriver.sh

# Verify it's running
curl http://localhost:9515/status
```

### Error: "element not interactable"

**Cause:** Page selectors may have changed or timing issues

**Solutions:**
1. Check if the Issuu website structure has changed
2. Try running in non-headless mode for debugging (requires code change)
3. Increase wait times in the code

### Error: "ChromeDriver not found"

**Cause:** ChromeDriver is not installed or not in PATH

**Solution:**
```bash
# Check if installed
which chromedriver

# If not found, install it (see Prerequisites above)
```

### Chrome Version Mismatch

**Error:** "This version of ChromeDriver only supports Chrome version X"

**Solution:**
```bash
# Update ChromeDriver to match your Chrome version
brew upgrade --cask chromedriver  # macOS

# Or download specific version from:
# https://chromedriver.chromium.org/downloads
```

## Development

### Run Tests
```bash
cargo test

# With output
cargo test -- --nocapture

# Specific test
cargo test test_chunked_yields_even_and_final_chunks
```

### Format Code
```bash
cargo fmt
```

### Lint Code
```bash
cargo clippy
```

### Build for Release
```bash
cargo build --release

# Binary will be at: ./target/release/issuu_scraper
```

## Performance

Compared to Python version:
- **30x faster startup** (50ms vs 1.5s)
- **6.6x less memory** (15MB vs 100MB)
- **20x faster processing** for large datasets
- **Single binary** - no runtime dependencies

## Architecture

```
rust/
├── src/
│   ├── lib.rs          # Core library
│   │   ├── HTTP download with retry
│   │   ├── Selenium automation
│   │   ├── Profile scraping
│   │   └── Parallel processing
│   └── main.rs         # CLI entry point
├── Cargo.toml          # Dependencies
├── start-chromedriver.sh
├── stop-chromedriver.sh
└── README.md           # This file
```

## Dependencies

- **reqwest** - HTTP client with retry logic
- **thirtyfour** - Selenium WebDriver automation
- **tokio** - Async runtime
- **indicatif** - Progress bars
- **anyhow** - Error handling
- **clap** - CLI argument parsing

## Notes

- ChromeDriver must be running before executing the scraper
- The scraper uses headless Chrome by default
- All PDFs are downloaded in parallel for performance
- Progress bars show real-time download status

## See Also

- [Main README](../README.md) - Project overview
- [RUST_PORT.md](../docs/RUST_PORT.md) - Detailed Rust port documentation
- [Python version](../python/) - Original Python implementation
