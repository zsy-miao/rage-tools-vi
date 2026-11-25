use annoyed_tools::{archive::Archive, verify};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc,
};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args: Vec<_> = std::env::args_os().skip(1).collect();
    let mut show_progress = false;
    let mut expected = None;
    loop {
        if args.first().is_some_and(|arg| arg == "--progress") {
            args.remove(0);
            show_progress = true;
        } else if args.first().is_some_and(|arg| arg == "--expect") {
            args.remove(0);
            if args.is_empty() {
                return Err("--expect requires a baseline path".into());
            }
            expected = Some(args.remove(0));
        } else {
            break;
        }
    }
    if args.len() != 2 {
        return Err(
            "usage: annoyed-verify [--progress] [--expect BASELINE.tsv] ARCHIVE INDEX.tsv".into(),
        );
    }
    let expected = expected
        .map(|path| verify::Baseline::read(Path::new(&path)))
        .transpose()?;
    let archive = Archive::open(Path::new(&args[0]))?;
    let progress = Arc::new(AtomicU64::new(0));
    let done = Arc::new(AtomicBool::new(false));
    if show_progress {
        let progress = progress.clone();
        let done = done.clone();
        let size = archive.size;
        std::thread::spawn(move || loop {
            std::thread::sleep(std::time::Duration::from_secs(5));
            if done.load(Ordering::Relaxed) {
                break;
            }
            let current = progress.load(Ordering::Relaxed);
            if current >= size {
                eprintln!("range checks complete; hashing archive and index");
            } else {
                eprintln!(
                    "checked {current}/{size} archive bytes ({:.1}%)",
                    100.0 * current as f64 / size as f64
                );
            }
        });
    }
    let result = verify::run(
        &archive,
        Path::new(&args[1]),
        Arc::new(AtomicBool::new(false)),
        progress,
    );
    done.store(true, Ordering::Relaxed);
    let report = result?;
    if let Some(baseline) = expected {
        baseline.compare(&report)?;
    }
    report.write_tsv(&mut std::io::stdout().lock())?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
