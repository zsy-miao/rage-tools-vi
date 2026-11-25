use annoyed_tools::{archive::Archive, index, search::Matcher};
use std::io::{self, Write};
use std::path::Path;

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 3 {
        return Err(
            "usage: annoyed-search ARCHIVE INDEX.tsv TEXT (case-sensitive UTF-8 bytes)".into(),
        );
    }
    let archive = Archive::open(Path::new(&args[0]))?;
    let index_path = Path::new(&args[1]);
    let query = args[2]
        .to_str()
        .ok_or("Search text must be UTF-8")?
        .as_bytes();
    if query.is_empty() {
        return Err("Search text is empty".into());
    }
    index::check_archive_size(index_path, archive.size)?;
    let mut archive_reader = archive.reader()?;
    let mut output = io::BufWriter::new(io::stdout().lock());
    writeln!(output, "start\tend\tdecoded_bytes\tkind")?;
    let mut position = 0;
    loop {
        let page = index::page(index_path, position, "")?;
        for range in page.rows {
            if range.kind != "zlib" && range.kind != "raw_deflate" {
                continue;
            }
            let mut matcher = Matcher::new(query)?;
            if range.kind == "raw_deflate" {
                archive_reader.decode_deflate_into(range.start, range.end, &mut matcher)?;
            } else {
                archive_reader.decode_zlib_into(range.start, range.end, &mut matcher)?;
            }
            if matcher.found() {
                writeln!(
                    output,
                    "0x{:x}\t0x{:x}\t{}\t{}",
                    range.start, range.end, range.decoded, range.kind
                )?;
                output.flush()?;
            }
        }
        match page.next {
            Some(next) => position = next,
            None => break,
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
