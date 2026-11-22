use annoyed_tools::{archive::Archive, indexer, resume};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicU64},
    Arc,
};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args: Vec<_> = std::env::args_os().skip(1).collect();
    let resumable = args.first().is_some_and(|arg| arg == "--resume");
    if resumable {
        args.remove(0);
    }
    if args.len() != 2 {
        return Err("usage: annoyed-index [--resume] ARCHIVE OUTPUT.tsv".into());
    }
    let archive = Archive::open(Path::new(&args[0]))?;
    let cancel = Arc::new(AtomicBool::new(false));
    let progress = Arc::new(AtomicU64::new(0));
    let count = if resumable {
        resume::create(&archive, Path::new(&args[1]), cancel, progress)?
    } else {
        indexer::create(&archive, Path::new(&args[1]), cancel, progress)?
    };
    println!("{count} zlib streams indexed");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
