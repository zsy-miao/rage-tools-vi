use annoyed_tools::archive::Archive;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU64};

fn offset(value: &str) -> Result<u64, Box<dyn std::error::Error>> {
    Ok(if let Some(hex) = value.strip_prefix("0x") {
        u64::from_str_radix(hex, 16)?
    } else {
        value.parse()?
    })
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 5
        || !["raw", "zlib", "deflate"]
            .iter()
            .any(|mode| args[0] == *mode)
    {
        return Err(
            "usage: annoyed-extract raw|zlib|deflate ARCHIVE START END OUTPUT (end exclusive; raw deflate has no checksum)".into(),
        );
    }
    let archive = Archive::open(Path::new(&args[1]))?;
    let start = offset(args[2].to_str().ok_or("invalid start offset")?)?;
    let end = offset(args[3].to_str().ok_or("invalid end offset")?)?;
    let output = Path::new(&args[4]);
    let bytes = if args[0] == "raw" {
        archive.export_raw(start, end, output)?
    } else if args[0] == "zlib" {
        archive.export_zlib(start, end, output)?
    } else {
        archive.export_deflate_cancellable(
            start,
            end,
            output,
            &AtomicBool::new(false),
            &AtomicU64::new(0),
        )?
    };
    println!("{bytes} bytes exported");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
