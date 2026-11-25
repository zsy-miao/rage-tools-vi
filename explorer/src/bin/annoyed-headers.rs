use annoyed_tools::{archive::Archive, headers};
use std::io::{self, Write};
use std::path::Path;

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 {
        return Err("usage: annoyed-headers ARCHIVE".into());
    }
    let archive = Archive::open(Path::new(&args[0]))?;
    let mut stdout = io::BufWriter::new(io::stdout().lock());
    writeln!(
        stdout,
        "offset\tfront_bytes\ttrailer_bytes\tdeclared_entries"
    )?;
    let mut position = 0;
    loop {
        let page = headers::scan(&archive, position)?;
        for header in page.headers {
            writeln!(
                stdout,
                "0x{:x}\t{}\t{}\t{}",
                header.offset, header.front_bytes, header.trailer_bytes, header.declared_entries
            )?;
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
