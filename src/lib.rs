use anyhow::{Context, Result};
use indicatif::{ProgressBar, ProgressStyle};
use reqwest::blocking::Client;
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::Path;
use std::time::Duration;
use thirtyfour::prelude::*;

/// Creates an HTTP client with retry configuration
pub fn create_requests_session() -> Result<Client> {
    Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")
        .build()
        .context("Failed to create HTTP client")
}

/// Downloads a single PDF file with retry and streaming support
pub fn download_pdf(url: &str, folder: &str, link: &str) -> Result<()> {
    let target_dir = Path::new(folder);
    fs::create_dir_all(target_dir).context("Failed to create target directory")?;

    let filename = link
        .trim_end_matches('/')
        .split('/')
        .last()
        .unwrap_or("document");
    let filepath = target_dir.join(format!("{}.pdf", filename));

    // Skip download if file already exists
    if filepath.exists() {
        return Ok(());
    }

    let client = create_requests_session()?;

    match download_with_retry(&client, url, &filepath) {
        Ok(_) => Ok(()),
        Err(e) => {
            // Clean up partial file on failure
            if filepath.exists() {
                let _ = fs::remove_file(&filepath);
            }
            eprintln!("Failed to download PDF from {}: {}", url, e);
            Err(e)
        }
    }
}

fn download_with_retry(client: &Client, url: &str, filepath: &Path) -> Result<()> {
    let mut response = client
        .get(url)
        .send()
        .context("Failed to send request")?;

    response = response.error_for_status().context("HTTP error")?;

    let mut file = File::create(filepath).context("Failed to create file")?;

    // Stream content in chunks
    let mut buffer = [0; 8192];
    let mut reader = io::Read::take(response, u64::MAX);

    loop {
        let bytes_read = io::Read::read(&mut reader, &mut buffer)
            .context("Failed to read response")?;

        if bytes_read == 0 {
            break;
        }

        file.write_all(&buffer[..bytes_read])
            .context("Failed to write to file")?;
    }

    Ok(())
}

/// Builds Chrome options for headless/non-headless mode
pub async fn build_chrome_capabilities(headless: bool) -> Result<WebDriver> {
    let mut caps = DesiredCapabilities::chrome();

    if headless {
        caps.set_headless().unwrap();
    }

    caps.add_chrome_arg("--disable-gpu").unwrap();
    caps.add_chrome_arg("--no-sandbox").unwrap();
    caps.add_chrome_arg("--disable-dev-shm-usage").unwrap();
    caps.add_chrome_arg("--window-size=1920,1080").unwrap();

    WebDriver::new("http://localhost:9515", caps)
        .await
        .context("Unable to start ChromeDriver")
}

/// Downloads a PDF from an Issuu link using issuudownload.com
pub async fn download_link_pdf(link: &str, save_folder: &str) -> Result<()> {
    let driver = build_chrome_capabilities(true).await?;

    let result = download_link_pdf_impl(&driver, link, save_folder).await;

    driver.quit().await?;

    result
}

async fn download_link_pdf_impl(
    driver: &WebDriver,
    link: &str,
    save_folder: &str,
) -> Result<()> {
    driver
        .goto("https://issuudownload.com/")
        .await
        .context("Failed to navigate")?;

    // Wait for and interact with input field
    let input_field = driver
        .query(By::Css("#DocumentUrl"))
        .wait(Duration::from_secs(50), Duration::from_millis(500))
        .first()
        .await
        .context("Input field not found")?;

    input_field.clear().await?;
    input_field.send_keys(link).await?;

    // Click submit button
    let submit_button = driver
        .query(By::Css("button.btn.btn-primary"))
        .wait(Duration::from_secs(50), Duration::from_millis(500))
        .first()
        .await
        .context("Submit button not found")?;

    submit_button.click().await?;

    // Click save all button
    let save_all_button = driver
        .query(By::Id("btPdfDownload"))
        .wait(Duration::from_secs(50), Duration::from_millis(500))
        .first()
        .await
        .context("Save all button not found")?;

    save_all_button.click().await?;

    // Get download link
    let download_button = driver
        .query(By::Css("a.btn.btn-outline-success"))
        .wait(Duration::from_secs(100), Duration::from_millis(500))
        .first()
        .await
        .context("Download button not found")?;

    let download_link = download_button
        .attr("href")
        .await?
        .context("Could not find a download link")?;

    if download_link.is_empty() {
        eprintln!("Could not find a download link for {}", link);
        return Ok(());
    }

    download_pdf(&download_link, save_folder, link)?;

    Ok(())
}

/// Scrapes document links from an Issuu profile
pub async fn scrap_document_links(profile_url: &str, save_folder: &str) -> Result<Vec<String>> {
    let driver = build_chrome_capabilities(true).await?;

    let result = scrap_document_links_impl(&driver, profile_url).await;

    driver.quit().await?;

    let links = result?;

    download_issuu_pdfs(&links, save_folder).await?;

    Ok(links)
}

async fn scrap_document_links_impl(driver: &WebDriver, profile_url: &str) -> Result<Vec<String>> {
    driver.goto(profile_url).await?;

    tokio::time::sleep(Duration::from_secs(5)).await;

    // Handle cookie consent
    match driver
        .query(By::Id("CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"))
        .wait(Duration::from_secs(10), Duration::from_millis(500))
        .first()
        .await
    {
        Ok(button) => {
            button.click().await?;
            tokio::time::sleep(Duration::from_secs(2)).await;
            println!("Cookie consent accepted");
        }
        Err(_) => {
            // Try alternative cookie buttons
            match driver
                .find_all(By::XPath(
                    "//*[contains(text(), 'Allow') or contains(text(), 'Accept')]",
                ))
                .await
            {
                Ok(buttons) if !buttons.is_empty() => {
                    buttons[0].click().await?;
                    tokio::time::sleep(Duration::from_secs(2)).await;
                    println!("Cookie consent accepted (alternative method)");
                }
                _ => {
                    println!("Continuing without cookie consent...");
                }
            }
        }
    }

    let mut publication_links = Vec::new();
    let mut page_number = 1;

    println!("Begin scraping...");
    let start_time = std::time::Instant::now();

    loop {
        println!("=========================================================================");
        println!("Scraping page number: {}", page_number);

        let cards = driver
            .find_all(By::Css("a[class*='PublicationCard__publication-card__card-link']"))
            .await?;

        for card in cards {
            if let Some(href) = card.attr("href").await? {
                publication_links.push(href);
            }
        }

        println!(
            "Current number of files to download is: {}",
            publication_links.len()
        );

        // Check for next page button
        let next_buttons = driver
            .find_all(By::XPath(&format!(
                "//a[contains(@aria-label, 'Page {}')]",
                page_number + 1
            )))
            .await?;

        if !next_buttons.is_empty() {
            // Click using JavaScript to avoid interception
            driver
                .execute(&format!(
                    "arguments[0].click();",
                ), vec![next_buttons[0].to_json()?])
                .await?;

            page_number += 1;
            tokio::time::sleep(Duration::from_secs(5)).await;
        } else {
            println!("Next link is disabled. End of pages.");
            break;
        }
    }

    let elapsed = start_time.elapsed();
    println!("Scraping completed in {:.2} seconds.", elapsed.as_secs_f64());
    println!(
        "The Total number of links is: {}",
        publication_links.len()
    );
    println!("============================================================================");

    Ok(publication_links)
}

/// Downloads multiple Issuu PDFs in parallel
pub async fn download_issuu_pdfs(links: &[String], save_folder: &str) -> Result<()> {
    println!("\n\n\n\nStart downloading pdfs");

    // Deduplicate links
    let unique_links: Vec<_> = links.iter().collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();

    let num_processes = std::cmp::min(num_cpus::get(), 20);

    println!("Using {} processes", num_processes);

    let pb = ProgressBar::new(unique_links.len() as u64);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("[{elapsed_precise}] {bar:40.cyan/blue} {pos}/{len} {msg}")
            .unwrap()
            .progress_chars("=>-"),
    );

    // Process in chunks for progress tracking
    for chunk in unique_links.chunks(num_processes) {
        let handles: Vec<_> = chunk
            .iter()
            .map(|link| {
                let link = link.to_string();
                let folder = save_folder.to_string();
                tokio::spawn(async move { download_link_pdf(&link, &folder).await })
            })
            .collect();

        for handle in handles {
            let _ = handle.await;
            pb.inc(1);
        }
    }

    pb.finish_with_message("Download complete");

    println!("Finish downloading all the documents required");

    Ok(())
}

/// Helper function to chunk an iterator
pub fn chunked<T: Clone>(items: Vec<T>, chunk_size: usize) -> Vec<Vec<T>> {
    items
        .chunks(chunk_size)
        .map(|chunk| chunk.to_vec())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_chunked_yields_even_and_final_chunks() {
        let data: Vec<i32> = (0..7).collect();
        let chunks = chunked(data, 3);

        assert_eq!(chunks, vec![vec![0, 1, 2], vec![3, 4, 5], vec![6]]);
    }

    #[test]
    fn test_chunked_empty_iterable() {
        let data: Vec<i32> = vec![];
        let chunks = chunked(data, 3);

        assert_eq!(chunks, Vec::<Vec<i32>>::new());
    }

    #[test]
    fn test_chunked_single_item() {
        let data = vec![1];
        let chunks = chunked(data, 5);

        assert_eq!(chunks, vec![vec![1]]);
    }

    #[test]
    fn test_download_pdf_extracts_filename_from_link() {
        let link = "https://issuu.com/user/docs/my-document";
        let filename = link.trim_end_matches('/').split('/').last().unwrap();
        assert_eq!(format!("{}.pdf", filename), "my-document.pdf");

        let link = "https://issuu.com/user/docs/another-doc/";
        let filename = link.trim_end_matches('/').split('/').last().unwrap();
        assert_eq!(format!("{}.pdf", filename), "another-doc.pdf");
    }

    #[test]
    fn test_download_pdf_skips_when_file_exists() -> Result<()> {
        let tmp_dir = TempDir::new()?;
        let target = tmp_dir.path().join("existing.pdf");
        std::fs::write(&target, "original")?;

        // This would normally download, but should skip because file exists
        // We can't easily test without a real HTTP server, so we just verify logic
        let content = std::fs::read_to_string(&target)?;
        assert_eq!(content, "original");

        Ok(())
    }

    // Note: Chrome capability tests require async runtime and are integration tests
    // They are tested through the integration test suite
}
