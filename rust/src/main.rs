use anyhow::Result;
use clap::Parser;
use issuu_scraper::scrap_document_links;

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Issuu profile URL to scrape
    #[arg(short, long)]
    profile_url: String,

    /// Folder to save downloaded PDFs
    #[arg(short, long)]
    save_folder: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    scrap_document_links(&args.profile_url, &args.save_folder).await?;

    Ok(())
}
