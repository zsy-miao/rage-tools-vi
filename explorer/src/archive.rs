use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

struct ExportWriter<'a> {
    file: File,
    cancel: &'a AtomicBool,
    progress: &'a AtomicU64,
}

impl Write for ExportWriter<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.cancel.load(Ordering::Relaxed) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Export cancelled",
            ));
        }
        let written = self.file.write(bytes)?;
        self.progress.fetch_add(written as u64, Ordering::Relaxed);
        Ok(written)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.file.flush()
    }
}

fn write_fully(output: &mut impl Write, mut bytes: &[u8]) -> io::Result<()> {
    while !bytes.is_empty() {
        let written = output.write(bytes)?;
        if written == 0 {
            return Err(io::Error::new(
                io::ErrorKind::WriteZero,
                "Writer made no progress",
            ));
        }
        bytes = &bytes[written..];
    }
    Ok(())
}

fn atomic_export(
    destination: &Path,
    cancel: &AtomicBool,
    progress: &AtomicU64,
    operation: impl FnOnce(&mut ExportWriter<'_>) -> io::Result<u64>,
) -> io::Result<u64> {
    if cancel.load(Ordering::Relaxed) {
        return Err(io::Error::new(
            io::ErrorKind::Interrupted,
            "Export cancelled",
        ));
    }
    if destination.exists() {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "Destination already exists",
        ));
    }
    let mut temp_name = destination.as_os_str().to_owned();
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    temp_name.push(format!(".partial-{}-{nonce}", std::process::id()));
    let temp = PathBuf::from(temp_name);
    let file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)?;
    let mut output = ExportWriter {
        file,
        cancel,
        progress,
    };
    let result = operation(&mut output).and_then(|bytes| {
        if cancel.load(Ordering::Relaxed) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Export cancelled",
            ));
        }
        output.file.sync_all()?;
        Ok(bytes)
    });
    drop(output);
    let result = result.and_then(|bytes| {
        if cancel.load(Ordering::Relaxed) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Export cancelled",
            ));
        }
        std::fs::hard_link(&temp, destination)?;
        Ok(bytes)
    });
    let _ = std::fs::remove_file(temp);
    result
}

#[derive(Clone, Debug)]
pub struct Archive {
    pub path: PathBuf,
    pub size: u64,
    pub header: [u8; 96],
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn reads_high_offsets_without_loading_the_file() {
        let path =
            std::env::temp_dir().join(format!("rage-explorer-sparse-{}", std::process::id()));
        let mut file = File::create(&path).unwrap();
        let mut header = [0u8; 96];
        header[..4].copy_from_slice(b"9FPR");
        file.write_all(&header).unwrap();
        let offset = 1u64 << 40;
        file.seek(SeekFrom::Start(offset)).unwrap();
        file.write_all(b"test").unwrap();
        drop(file);
        let archive = Archive::open(&path).unwrap();
        assert_eq!(archive.read(offset, 4096).unwrap(), b"test");
        assert!(archive.read(offset + 4, 4096).unwrap().is_empty());
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn exports_complete_stream_and_rejects_truncation_and_overwrite() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../story000_bvh4.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let base = std::env::temp_dir().join(format!("annoyed-export-test-{}", std::process::id()));
        std::fs::create_dir_all(&base).unwrap();
        let good = base.join("good.xml");
        assert_eq!(archive.export_zlib(0x340, 0x4f1, &good).unwrap(), 800);
        assert!(archive.export_zlib(0x340, 0x4f1, &good).is_err());
        let bad = base.join("bad.xml");
        assert!(archive.export_zlib(0x340, 0x4f0, &bad).is_err());
        assert!(!bad.exists());
        std::fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn streams_decoded_payload_larger_than_legacy_cap() {
        use flate2::{write::ZlibEncoder, Compression};
        let base = std::env::temp_dir().join(format!("annoyed-large-{}", std::process::id()));
        std::fs::create_dir_all(&base).unwrap();
        let source = base.join("source.rpf");
        let mut file = File::create(&source).unwrap();
        let mut header = [0u8; 96];
        header[..4].copy_from_slice(b"9FPR");
        file.write_all(&header).unwrap();
        let mut encoder = ZlibEncoder::new(file, Compression::fast());
        let block = [b'X'; 65536];
        for _ in 0..320 {
            encoder.write_all(&block).unwrap();
        }
        encoder.finish().unwrap();
        let archive = Archive::open(&source).unwrap();
        assert!(archive
            .preview_zlib(96, archive.size)
            .unwrap()
            .starts_with("Decoded text preview (first 64 KiB)"));
        let destination = base.join("decoded.bin");
        assert_eq!(
            archive.export_zlib(96, archive.size, &destination).unwrap(),
            20 * 1024 * 1024
        );
        assert_eq!(
            std::fs::metadata(&destination).unwrap().len(),
            20 * 1024 * 1024
        );
        let cancelled = base.join("cancelled.bin");
        assert_eq!(
            archive
                .export_zlib_cancellable(
                    96,
                    archive.size,
                    &cancelled,
                    &AtomicBool::new(true),
                    &AtomicU64::new(0)
                )
                .unwrap_err()
                .kind(),
            io::ErrorKind::Interrupted
        );
        assert!(!cancelled.exists());
        std::fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn rejects_short_and_non_rpf_inputs() {
        let path = std::env::temp_dir().join(format!("annoyed-invalid-{}", std::process::id()));
        std::fs::write(&path, b"9FPR").unwrap();
        assert!(Archive::open(&path).is_err());
        std::fs::write(&path, [0u8; 96]).unwrap();
        assert!(Archive::open(&path).is_err());
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn drains_decoder_output_after_input_is_exhausted() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../data.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let decoded = archive
            .decode_zlib_into(0xa5f0e0, 0xa861d0, &mut io::sink())
            .unwrap();
        assert_eq!(decoded, 393216);
    }

    #[test]
    fn decodes_known_raw_deflate_control() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../data.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let mut reader = archive.reader().unwrap();
        let mut bytes = Vec::new();
        assert_eq!(
            reader
                .decode_deflate_into(0x966000, 0x966308, &mut bytes)
                .unwrap(),
            1318
        );
        assert!(bytes.starts_with(b"RBF0"));
    }

    #[test]
    fn cancellation_does_not_publish_partial_export() {
        use std::sync::Arc;
        let base =
            std::env::temp_dir().join(format!("annoyed-cancel-export-{}", std::process::id()));
        std::fs::create_dir_all(&base).unwrap();
        let source = base.join("source.rpf");
        let mut file = File::create(&source).unwrap();
        let mut header = [0u8; 96];
        header[..4].copy_from_slice(b"9FPR");
        file.write_all(&header).unwrap();
        file.set_len(64 * 1024 * 1024).unwrap();
        drop(file);
        let archive = Archive::open(&source).unwrap();
        let cancel = Arc::new(AtomicBool::new(false));
        let progress = Arc::new(AtomicU64::new(0));
        let watcher_cancel = cancel.clone();
        let watcher_progress = progress.clone();
        let watcher = std::thread::spawn(move || {
            let started = std::time::Instant::now();
            while watcher_progress.load(Ordering::Relaxed) < 65536
                && started.elapsed() < std::time::Duration::from_secs(5)
            {
                std::thread::yield_now();
            }
            watcher_cancel.store(true, Ordering::Relaxed);
        });
        let destination = base.join("payload.bin");
        let result =
            archive.export_raw_cancellable(96, archive.size, &destination, &cancel, &progress);
        watcher.join().unwrap();
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::Interrupted);
        assert!(!destination.exists());
        assert_eq!(std::fs::read_dir(&base).unwrap().count(), 1);
        std::fs::remove_dir_all(base).unwrap();
    }
}

impl Archive {
    pub fn open(path: &Path) -> io::Result<Self> {
        let mut file = File::open(path)?;
        let size = file.metadata()?.len();
        let mut header = [0; 96];
        file.read_exact(&mut header)?;
        if &header[..4] != b"9FPR" {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Expected RPF9 signature",
            ));
        }
        Ok(Self {
            path: path.to_owned(),
            size,
            header,
        })
    }

    pub fn read(&self, offset: u64, length: usize) -> io::Result<Vec<u8>> {
        let mut file = File::open(&self.path)?;
        file.seek(SeekFrom::Start(offset))?;
        let available = self.size.saturating_sub(offset).min(length as u64) as usize;
        let mut bytes = vec![0; available];
        file.read_exact(&mut bytes)?;
        Ok(bytes)
    }

    pub fn word(&self, offset: usize) -> u32 {
        u32::from_le_bytes(self.header[offset..offset + 4].try_into().unwrap())
    }

    pub fn preview_zlib(&self, start: u64, end: u64) -> io::Result<String> {
        self.preview_compressed(start, end, false)
    }

    pub fn preview_deflate(&self, start: u64, end: u64) -> io::Result<String> {
        self.preview_compressed(start, end, true)
    }

    pub fn decoded_prefix(&self, start: u64, end: u64, raw: bool, limit: usize) -> io::Result<(Vec<u8>, bool)> {
        if end > self.size || end <= start || limit > 8 * 1024 * 1024 { return Err(io::Error::new(io::ErrorKind::InvalidInput, "Invalid range or preview limit")); }
        let mut file = File::open(&self.path)?;
        file.seek(SeekFrom::Start(start))?;
        let input = file.take(end - start);
        let decoder: Box<dyn Read> = if raw { Box::new(flate2::read::DeflateDecoder::new(input)) } else { Box::new(flate2::read::ZlibDecoder::new(input)) };
        let mut bytes = Vec::new();
        decoder.take(limit as u64 + 1).read_to_end(&mut bytes)?;
        let truncated = bytes.len() > limit;
        bytes.truncate(limit);
        Ok((bytes, truncated))
    }

    fn preview_compressed(&self, start: u64, end: u64, raw: bool) -> io::Result<String> {
        if end > self.size || end <= start {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Range outside archive",
            ));
        }
        let mut file = File::open(&self.path)?;
        file.seek(SeekFrom::Start(start))?;
        let input = file.take(end - start);
        let decoder: Box<dyn Read> = if raw {
            Box::new(flate2::read::DeflateDecoder::new(input))
        } else {
            Box::new(flate2::read::ZlibDecoder::new(input))
        };
        let mut bytes = Vec::new();
        decoder.take(65537).read_to_end(&mut bytes)?;
        let truncated = bytes.len() > 65536;
        bytes.truncate(65536);
        let text = match std::str::from_utf8(&bytes) {
            Err(error) if truncated && error.error_len().is_none() => {
                std::str::from_utf8(&bytes[..error.valid_up_to()])
            }
            other => other,
        };
        match text {
            Ok(text)
                if text
                    .chars()
                    .all(|c| !c.is_control() || c.is_ascii_whitespace()) =>
            {
                Ok(format!(
                    "Decoded text preview{}{}\n\n{}",
                    if truncated { " (first 64 KiB)" } else { "" },
                    if raw {
                        " (raw DEFLATE has no checksum)"
                    } else {
                        ""
                    },
                    text
                ))
            }
            _ => {
                let mut result = if raw {
                    String::from("Decoded content is binary (raw DEFLATE has no checksum); first 256 bytes:\n\n")
                } else {
                    String::from("Decoded content is binary; first 256 bytes:\n\n")
                };
                for (i, chunk) in bytes[..bytes.len().min(256)].chunks(16).enumerate() {
                    use std::fmt::Write as _;
                    let _ = write!(result, "{:08x}  ", i * 16);
                    for byte in chunk {
                        let _ = write!(result, "{byte:02x} ");
                    }
                    result.push('\n');
                }
                Ok(result)
            }
        }
    }

    pub fn export_zlib(&self, start: u64, end: u64, destination: &Path) -> io::Result<u64> {
        self.export_zlib_cancellable(
            start,
            end,
            destination,
            &AtomicBool::new(false),
            &AtomicU64::new(0),
        )
    }

    pub fn export_zlib_cancellable(
        &self,
        start: u64,
        end: u64,
        destination: &Path,
        cancel: &AtomicBool,
        progress: &AtomicU64,
    ) -> io::Result<u64> {
        if end > self.size || end <= start {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Range outside archive",
            ));
        }
        atomic_export(destination, cancel, progress, |output| {
            self.decode_zlib_into(start, end, output)
        })
    }

    pub fn decode_zlib_into(
        &self,
        start: u64,
        end: u64,
        output: &mut impl Write,
    ) -> io::Result<u64> {
        let mut input = File::open(&self.path)?;
        decode_from(&mut input, self.size, start, end, true, output)
    }

    /// Raw DEFLATE has no checksum; stream termination does not prove identity.
    pub fn export_deflate_cancellable(
        &self,
        start: u64,
        end: u64,
        destination: &Path,
        cancel: &AtomicBool,
        progress: &AtomicU64,
    ) -> io::Result<u64> {
        if end > self.size || end <= start {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Range outside archive",
            ));
        }
        atomic_export(destination, cancel, progress, |output| {
            let mut input = File::open(&self.path)?;
            decode_from(&mut input, self.size, start, end, false, output)
        })
    }

    pub fn reader(&self) -> io::Result<ArchiveReader> {
        Ok(ArchiveReader {
            file: File::open(&self.path)?,
            size: self.size,
        })
    }

    pub fn export_raw(&self, start: u64, end: u64, destination: &Path) -> io::Result<u64> {
        self.export_raw_cancellable(
            start,
            end,
            destination,
            &AtomicBool::new(false),
            &AtomicU64::new(0),
        )
    }

    pub fn export_raw_cancellable(
        &self,
        start: u64,
        end: u64,
        destination: &Path,
        cancel: &AtomicBool,
        progress: &AtomicU64,
    ) -> io::Result<u64> {
        if end > self.size || end <= start {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Range outside archive",
            ));
        }
        let mut input = File::open(&self.path)?;
        input.seek(SeekFrom::Start(start))?;
        atomic_export(destination, cancel, progress, |output| {
            let mut source = input.take(end - start);
            let mut buffer = [0u8; 65536];
            let mut total = 0;
            loop {
                if cancel.load(Ordering::Relaxed) {
                    return Err(io::Error::new(
                        io::ErrorKind::Interrupted,
                        "Export cancelled",
                    ));
                }
                let n = source.read(&mut buffer)?;
                if n == 0 {
                    break;
                }
                write_fully(output, &buffer[..n])?;
                total += n as u64;
            }
            if total == end - start {
                Ok(total)
            } else {
                Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "Archive changed during export",
                ))
            }
        })
    }
}

pub struct ArchiveReader {
    file: File,
    size: u64,
}
impl ArchiveReader {
    pub fn decode_zlib_into(
        &mut self,
        start: u64,
        end: u64,
        output: &mut impl Write,
    ) -> io::Result<u64> {
        decode_from(&mut self.file, self.size, start, end, true, output)
    }
    pub fn decode_deflate_into(
        &mut self,
        start: u64,
        end: u64,
        output: &mut impl Write,
    ) -> io::Result<u64> {
        decode_from(&mut self.file, self.size, start, end, false, output)
    }
}

fn decode_from(
    input: &mut File,
    size: u64,
    start: u64,
    end: u64,
    zlib_header: bool,
    output: &mut impl Write,
) -> io::Result<u64> {
    if end > size || end <= start {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Range outside archive",
        ));
    }
    input.seek(SeekFrom::Start(start))?;
    {
        let mut reader = input.take(end - start);
        let mut decoder = flate2::Decompress::new(zlib_header);
        let mut input_buf = [0u8; 65536];
        let mut output_buf = [0u8; 65536];
        let mut pos = 0usize;
        let mut filled = 0usize;
        let mut exhausted = false;
        loop {
            if pos == filled && !exhausted {
                filled = reader.read(&mut input_buf)?;
                pos = 0;
                exhausted = filled == 0;
            }
            let before_in = decoder.total_in();
            let before_out = decoder.total_out();
            let status = decoder
                .decompress(
                    &input_buf[pos..filled],
                    &mut output_buf,
                    if exhausted {
                        flate2::FlushDecompress::Finish
                    } else {
                        flate2::FlushDecompress::None
                    },
                )
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
            let consumed = (decoder.total_in() - before_in) as usize;
            let produced = (decoder.total_out() - before_out) as usize;
            write_fully(output, &output_buf[..produced])?;
            pos += consumed;
            if status == flate2::Status::StreamEnd {
                if decoder.total_in() != end - start {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "Range contains trailing bytes",
                    ));
                }
                return Ok(decoder.total_out());
            }
            if consumed == 0 && produced == 0 {
                return Err(io::Error::new(
                    if exhausted {
                        io::ErrorKind::UnexpectedEof
                    } else {
                        io::ErrorKind::InvalidData
                    },
                    if exhausted {
                        "Incomplete DEFLATE stream"
                    } else {
                        "DEFLATE decoder made no progress"
                    },
                ));
            }
        }
    }
}
