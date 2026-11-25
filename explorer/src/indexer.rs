use crate::archive::Archive;
use flate2::{Decompress, FlushDecompress, Status};
use std::fs::{File, OpenOptions};
use std::io::{self, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc,
};

const BLOCK: usize = 65536;

fn label(preview: &[u8]) -> String {
    let utf8 = match std::str::from_utf8(preview) {
        Ok(text) => Ok(text),
        Err(error) if error.error_len().is_none() => {
            std::str::from_utf8(&preview[..error.valid_up_to()])
        }
        Err(error) => Err(error),
    };
    match utf8 {
        Ok(s)
            if s.chars()
                .all(|c| !c.is_control() || c.is_ascii_whitespace()) =>
        {
            s.split_whitespace().collect::<Vec<_>>().join(" ")
        }
        _ => String::new(),
    }
}

pub(crate) fn zlib_end(
    file: &mut File,
    start: u64,
    limit: u64,
    cancel: &AtomicBool,
) -> io::Result<Option<(u64, u64, String)>> {
    file.seek(SeekFrom::Start(start))?;
    let mut decoder = Decompress::new(true);
    let mut input = [0; BLOCK];
    let mut output = [0; BLOCK];
    let mut read = 0u64;
    let mut preview = Vec::with_capacity(512);
    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Indexing cancelled",
            ));
        }
        let n = file.read(&mut input[..(limit - start - read).min(BLOCK as u64) as usize])?;
        if n == 0 {
            loop {
                let before = decoder.total_out();
                let status = match decoder.decompress(&[], &mut output, FlushDecompress::Finish) {
                    Ok(status) => status,
                    Err(_) => return Ok(None),
                };
                let produced = (decoder.total_out() - before) as usize;
                let take = produced.min(512 - preview.len());
                preview.extend_from_slice(&output[..take]);
                if status == Status::StreamEnd {
                    return Ok(Some((
                        start + decoder.total_in(),
                        decoder.total_out(),
                        label(&preview),
                    )));
                }
                if produced == 0 {
                    return Ok(None);
                }
                if cancel.load(Ordering::Relaxed) {
                    return Err(io::Error::new(
                        io::ErrorKind::Interrupted,
                        "Indexing cancelled",
                    ));
                }
            }
        }
        read += n as u64;
        let mut pos = 0;
        while pos < n {
            let before_in = decoder.total_in();
            let before_out = decoder.total_out();
            let status =
                match decoder.decompress(&input[pos..n], &mut output, FlushDecompress::None) {
                    Ok(status) => status,
                    Err(_) => return Ok(None),
                };
            pos += (decoder.total_in() - before_in) as usize;
            let produced = (decoder.total_out() - before_out) as usize;
            let take = produced.min(512 - preview.len());
            preview.extend_from_slice(&output[..take]);
            if status == Status::StreamEnd {
                return Ok(Some((
                    start + decoder.total_in(),
                    decoder.total_out(),
                    label(&preview),
                )));
            }
            if decoder.total_in() == before_in && decoder.total_out() == before_out {
                return Ok(None);
            }
        }
    }
}

pub fn create(
    archive: &Archive,
    path: &Path,
    cancel: Arc<AtomicBool>,
    progress: Arc<AtomicU64>,
) -> io::Result<u64> {
    let front = archive.word(4) as u64;
    let trailer = archive.word(12) as u64;
    if front < 96 || front > archive.size || trailer > archive.size - front {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid front or trailer bounds",
        ));
    }
    let end = archive.size - trailer;
    let file = OpenOptions::new().write(true).create_new(true).open(path)?;
    let result = (|| {
        let mut output = BufWriter::new(file);
        writeln!(
            output,
            "kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\ttext_prefix"
        )?;
        writeln!(output, "front\t0x0\t0x{front:x}\t{front}\t\t")?;
        let mut source = File::open(&archive.path)?;
        let mut buffer = [0u8; BLOCK];
        let mut cursor = front;
        let mut pos = front;
        let mut count = 0;
        while pos < end {
            progress.store(pos, Ordering::Relaxed);
            if cancel.load(Ordering::Relaxed) {
                return Err(io::Error::new(
                    io::ErrorKind::Interrupted,
                    "Indexing cancelled",
                ));
            }
            source.seek(SeekFrom::Start(pos))?;
            let n = source.read(&mut buffer[..(end - pos).min(BLOCK as u64) as usize])?;
            if n == 0 {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "Archive changed during indexing",
                ));
            }
            let mut found = None;
            for i in 0..n {
                let offset = pos + i as u64;
                if offset % 16 != 0 || buffer[i] != 0x78 {
                    continue;
                }
                if let Some((stream_end, decoded, label)) =
                    zlib_end(&mut source, offset, end, &cancel)?
                {
                    found = Some((offset, stream_end, decoded, label));
                    break;
                }
            }
            if let Some((start, stream_end, decoded, label)) = found {
                if cursor < start {
                    writeln!(
                        output,
                        "unclassified\t0x{cursor:x}\t0x{start:x}\t{}\t\t",
                        start - cursor
                    )?;
                }
                writeln!(
                    output,
                    "zlib\t0x{start:x}\t0x{stream_end:x}\t{}\t{decoded}\t0x{start:x}\t{label}",
                    stream_end - start
                )?;
                cursor = stream_end;
                pos = stream_end;
                count += 1;
            } else {
                pos += n as u64;
            }
        }
        if cursor < end {
            writeln!(
                output,
                "unclassified\t0x{cursor:x}\t0x{end:x}\t{}\t\t",
                end - cursor
            )?;
        }
        if trailer > 0 {
            writeln!(
                output,
                "trailer\t0x{end:x}\t0x{:x}\t{trailer}\t\t",
                archive.size
            )?;
        }
        output.flush()?;
        Ok(count)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(path);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn control_index_and_cancellation() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../story000_bvh4.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let directory =
            std::env::temp_dir().join(format!("annoyed-indexer-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("index.tsv");
        assert_eq!(
            create(
                &archive,
                &path,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap(),
            4
        );
        let text = std::fs::read_to_string(&path).unwrap();
        for range in [
            "0x340\t0x4f1",
            "0x1000\t0x1291",
            "0x12a0\t0x13bd",
            "0x13c0\t0x1564",
        ] {
            assert!(text.contains(range));
        }
        let cancelled = directory.join("cancelled.tsv");
        assert_eq!(
            create(
                &archive,
                &cancelled,
                Arc::new(AtomicBool::new(true)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::Interrupted
        );
        assert!(!cancelled.exists());
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn detects_stream_ending_at_scan_limit() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../data.rpf");
        if !source.exists() {
            return;
        }
        let mut file = File::open(source).unwrap();
        let (end, decoded, _) = zlib_end(&mut file, 0xa5f0e0, 0xa861d0, &AtomicBool::new(false))
            .unwrap()
            .unwrap();
        assert_eq!((end, decoded), (0xa861d0, 393216));
    }

    #[test]
    #[ignore = "scans the local data.rpf corpus"]
    fn local_data_corpus() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../data.rpf");
        let archive = Archive::open(&source).unwrap();
        let directory = std::env::temp_dir().join(format!("annoyed-corpus-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("index.tsv");
        let started = std::time::Instant::now();
        let count = create(
            &archive,
            &path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        eprintln!(
            "data.rpf: {count} streams, {} bytes, {:?}",
            archive.size,
            started.elapsed()
        );
        assert_eq!(count, 28509);
        if std::env::var_os("ANNOYED_SKIP_BASELINE").is_some() {
            std::fs::remove_dir_all(directory).unwrap();
            return;
        }
        let baseline = directory.join("baseline.tsv");
        let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../tools/stream_index.py");
        assert!(std::process::Command::new("python3")
            .arg(script)
            .arg(&source)
            .arg("--out")
            .arg(&baseline)
            .status()
            .unwrap()
            .success());
        use std::io::{BufRead, BufReader};
        let actual = BufReader::new(File::open(&path).unwrap());
        let expected = BufReader::new(File::open(&baseline).unwrap());
        let streams = |reader: BufReader<File>| {
            reader
                .lines()
                .map(|line| line.unwrap())
                .filter(|line| line.starts_with("zlib\t"))
                .map(|line| {
                    line.split('\t')
                        .take(5)
                        .map(str::to_owned)
                        .collect::<Vec<_>>()
                })
        };
        let mut actual = streams(actual);
        let mut expected = streams(expected);
        loop {
            match (actual.next(), expected.next()) {
                (Some(a), Some(b)) => assert_eq!(a, b),
                (None, None) => break,
                _ => panic!("Stream counts differ"),
            }
        }
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    #[ignore = "scans the local 4.4 GB anim.rpf corpus"]
    fn local_anim_corpus() {
        use std::io::{BufRead, BufReader};
        let source =
            Path::new("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf");
        let baseline = Path::new(env!("CARGO_MANIFEST_DIR")).join("../output/index/anim.tsv");
        let archive = Archive::open(source).unwrap();
        let directory = std::env::temp_dir().join(format!("annoyed-anim-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("index.tsv");
        let started = std::time::Instant::now();
        let count = create(
            &archive,
            &path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        eprintln!(
            "anim.rpf: {count} streams, {} bytes, {:?}",
            archive.size,
            started.elapsed()
        );
        assert_eq!(count, 130510);
        let streams = |path: &Path| {
            BufReader::new(File::open(path).unwrap())
                .lines()
                .map(|line| line.unwrap())
                .filter(|line| line.starts_with("zlib\t"))
                .map(|line| {
                    line.split('\t')
                        .take(5)
                        .map(str::to_owned)
                        .collect::<Vec<_>>()
                })
        };
        let mut actual = streams(&path);
        let mut expected = streams(&baseline);
        loop {
            match (actual.next(), expected.next()) {
                (Some(a), Some(b)) => assert_eq!(a, b),
                (None, None) => break,
                _ => panic!("Stream counts differ"),
            }
        }
        std::fs::remove_dir_all(directory).unwrap();
    }
}
