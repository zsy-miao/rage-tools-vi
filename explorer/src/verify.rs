//! Bounded, opt-in validation of indexed ranges and archive bytes.
use crate::{archive::Archive, index};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::Write;
use std::io::{self, Read, Seek, SeekFrom};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc,
};

#[derive(Debug, Clone)]
pub struct Report {
    pub ranges: u64,
    pub zlib_streams: u64,
    pub raw_deflate_streams: u64,
    pub archive_bytes: u64,
    pub unclassified_bytes: u64,
    pub unchecked_bytes: u64,
    pub archive_sha256: String,
    pub index_sha256: String,
}

pub struct Baseline {
    archive_hash: String,
    index_hash: String,
}

impl Baseline {
    pub fn read(path: &Path) -> io::Result<Self> {
        let file = File::open(path)?;
        if file.metadata()?.len() > 65536 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Baseline is too large",
            ));
        }
        let mut text = String::new();
        file.take(65537).read_to_string(&mut text)?;
        if text.len() > 65536 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Baseline is too large",
            ));
        }
        let mut archive_hash = None;
        let mut index_hash = None;
        for line in text.lines() {
            let Some((key, value)) = line.split_once('\t') else {
                continue;
            };
            let slot = match key {
                "archive_sha256" => &mut archive_hash,
                "index_sha256" => &mut index_hash,
                _ => continue,
            };
            if slot.is_some() || value.len() != 64 || !value.bytes().all(|b| b.is_ascii_hexdigit())
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "Invalid baseline hash",
                ));
            }
            *slot = Some(value.to_ascii_lowercase());
        }
        Ok(Self {
            archive_hash: archive_hash.ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidData, "Baseline lacks archive hash")
            })?,
            index_hash: index_hash.ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidData, "Baseline lacks index hash")
            })?,
        })
    }
    pub fn compare(&self, report: &Report) -> io::Result<()> {
        if self.archive_hash != report.archive_sha256 || self.index_hash != report.index_sha256 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Archive or index differs from baseline",
            ));
        }
        Ok(())
    }
}

impl Report {
    pub fn write_tsv(&self, output: &mut impl Write) -> io::Result<()> {
        writeln!(output, "ranges\t{}\nzlib_streams\t{}\nraw_deflate_streams\t{}\narchive_bytes\t{}\nunclassified_bytes\t{}\nunchecked_bytes\t{}\narchive_sha256\t{}\nindex_sha256\t{}", self.ranges, self.zlib_streams, self.raw_deflate_streams, self.archive_bytes, self.unclassified_bytes, self.unchecked_bytes, self.archive_sha256, self.index_sha256)
    }

    pub fn compare_baseline(&self, path: &Path) -> io::Result<()> {
        Baseline::read(path)?.compare(self)
    }

    pub fn save_baseline(&self, path: &Path) -> io::Result<()> {
        let mut tmp = path.as_os_str().to_owned();
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        tmp.push(format!(".partial-{}-{nonce}", std::process::id()));
        let tmp = std::path::PathBuf::from(tmp);
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&tmp)?;
        let result = self.write_tsv(&mut file).and_then(|_| file.sync_all());
        drop(file);
        let result = result.and_then(|_| std::fs::hard_link(&tmp, path));
        let _ = std::fs::remove_file(tmp);
        result
    }
}

fn check(cancel: &AtomicBool) -> io::Result<()> {
    if cancel.load(Ordering::Relaxed) {
        Err(io::Error::new(
            io::ErrorKind::Interrupted,
            "Verification cancelled",
        ))
    } else {
        Ok(())
    }
}

struct Sink<'a>(&'a AtomicBool);
impl io::Write for Sink<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        check(self.0)?;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn hash(path: &Path, cancel: &AtomicBool) -> io::Result<String> {
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut bytes = [0u8; 65536];
    loop {
        check(cancel)?;
        let n = file.read(&mut bytes)?;
        if n == 0 {
            break;
        }
        digest.update(&bytes[..n]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub fn run(
    archive: &Archive,
    index_path: &Path,
    cancel: Arc<AtomicBool>,
    progress: Arc<AtomicU64>,
) -> io::Result<Report> {
    let before = std::fs::metadata(&archive.path)?;
    let index_before = std::fs::metadata(index_path)?;
    if before.len() != archive.size {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Archive size changed",
        ));
    }
    index::check_archive_size(index_path, archive.size)?;
    let mut reader = archive.reader()?;
    let mut zero_source = File::open(&archive.path)?;
    let mut zero_buffer = [0u8; 65536];
    let mut position = 0;
    let mut cursor = 0u64;
    let mut count = 0u64;
    let mut streams = 0u64;
    let mut raw_streams = 0u64;
    let mut unclassified = 0u64;
    let mut unchecked = 0u64;
    loop {
        check(&cancel)?;
        let page = index::page(index_path, position, "")?;
        for range in page.rows {
            check(&cancel)?;
            if range.start != cursor || range.end > archive.size {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("Invalid coverage at 0x{cursor:x}"),
                ));
            }
            if range.kind == "unclassified" {
                unclassified += range.end - range.start;
            }
            if range.kind != "zlib" && range.kind != "zero_run" {
                unchecked += range.end - range.start;
            }
            if range.kind == "zlib" || range.kind == "raw_deflate" {
                let expected: u64 = range.decoded.parse().map_err(|_| {
                    io::Error::new(io::ErrorKind::InvalidData, "Invalid decoded size")
                })?;
                let result = if range.kind == "zlib" {
                    reader.decode_zlib_into(range.start, range.end, &mut Sink(&cancel))
                } else {
                    reader.decode_deflate_into(range.start, range.end, &mut Sink(&cancel))
                };
                let actual = result.map_err(|error| {
                    io::Error::new(
                        error.kind(),
                        format!("{} at 0x{:x}: {error}", range.kind, range.start),
                    )
                })?;
                if actual != expected {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        format!("Decoded size mismatch at 0x{:x}", range.start),
                    ));
                }
                if range.kind == "zlib" {
                    streams += 1;
                } else {
                    raw_streams += 1;
                }
            } else if range.kind == "zero_run" {
                zero_source.seek(SeekFrom::Start(range.start))?;
                let mut left = range.end - range.start;
                while left > 0 {
                    check(&cancel)?;
                    let n = left.min(zero_buffer.len() as u64) as usize;
                    zero_source.read_exact(&mut zero_buffer[..n])?;
                    if zero_buffer[..n].iter().any(|&byte| byte != 0) {
                        return Err(io::Error::new(
                            io::ErrorKind::InvalidData,
                            format!("Nonzero bytes in zero range at 0x{:x}", range.start),
                        ));
                    }
                    left -= n as u64;
                }
            }
            cursor = range.end;
            progress.store(cursor, Ordering::Relaxed);
            count += 1;
        }
        match page.next {
            Some(next) => position = next,
            None => break,
        }
    }
    if cursor != archive.size {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Index does not cover the archive",
        ));
    }
    let archive_sha256 = hash(&archive.path, &cancel)?;
    let index_sha256 = hash(index_path, &cancel)?;
    let after = std::fs::metadata(&archive.path)?;
    if before.len() != after.len() || before.modified()? != after.modified()? {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Archive changed during verification",
        ));
    }
    let index_after = std::fs::metadata(index_path)?;
    if index_before.len() != index_after.len()
        || index_before.modified()? != index_after.modified()?
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Index changed during verification",
        ));
    }
    Ok(Report {
        ranges: count,
        zlib_streams: streams,
        raw_deflate_streams: raw_streams,
        archive_bytes: archive.size,
        unclassified_bytes: unclassified,
        unchecked_bytes: unchecked,
        archive_sha256,
        index_sha256,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn verifies_control_and_rejects_false_zero_run() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../story000_bvh4.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let directory = std::env::temp_dir().join(format!("annoyed-verify-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("index.tsv");
        crate::indexer::create(
            &archive,
            &path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        let report = run(
            &archive,
            &path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        assert_eq!(report.zlib_streams, 4);
        assert_eq!(
            report.archive_sha256,
            "b9f86219f835c769ca86274f933ab35423af45dad33f130d5c5e4727450ffd24"
        );
        let baseline = directory.join("baseline.tsv");
        report.save_baseline(&baseline).unwrap();
        assert_eq!(
            report.save_baseline(&baseline).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
        report.compare_baseline(&baseline).unwrap();
        let changed = std::fs::read_to_string(&path)
            .unwrap()
            .replace("Auto-Generated", "Auto-Genereted");
        std::fs::write(&path, changed).unwrap();
        let changed_report = run(
            &archive,
            &path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        assert_eq!(
            changed_report
                .compare_baseline(&baseline)
                .unwrap_err()
                .kind(),
            io::ErrorKind::InvalidData
        );
        let text = std::fs::read_to_string(&path)
            .unwrap()
            .replacen("front\t", "zero_run\t", 1);
        std::fs::write(&path, text).unwrap();
        assert_eq!(
            run(
                &archive,
                &path,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::InvalidData
        );
        std::fs::remove_dir_all(directory).unwrap();
    }
}
