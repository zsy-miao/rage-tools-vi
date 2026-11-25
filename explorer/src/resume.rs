//! Checkpointed index construction. Partial files are deliberately retained on pause.
use crate::{archive::Archive, indexer};
use sha2::{Digest, Sha256};
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc,
};
use std::time::{Duration, Instant, UNIX_EPOCH};

const BLOCK: usize = 65536;
const MAGIC: &[u8; 8] = b"ATIDX001";

fn sibling(path: &Path, suffix: &str) -> PathBuf {
    let mut name: OsString = path.as_os_str().to_owned();
    name.push(suffix);
    PathBuf::from(name)
}

fn fingerprint(archive: &Archive) -> io::Result<[u8; 32]> {
    let mut file = File::open(&archive.path)?;
    let metadata = file.metadata()?;
    if metadata.len() != archive.size {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Archive size changed",
        ));
    }
    let modified = metadata
        .modified()?
        .duration_since(UNIX_EPOCH)
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "Invalid source modification time",
            )
        })?;
    let mut hash = Sha256::new();
    hash.update(metadata.len().to_le_bytes());
    hash.update(modified.as_secs().to_le_bytes());
    hash.update(modified.subsec_nanos().to_le_bytes());
    hash.update(format!("{:?}", fs::canonicalize(&archive.path)?).as_bytes());
    let mut buffer = vec![0; metadata.len().min(BLOCK as u64) as usize];
    file.read_exact(&mut buffer)?;
    hash.update(&buffer);
    if metadata.len() > BLOCK as u64 {
        file.seek(SeekFrom::End(-(BLOCK as i64)))?;
        buffer.resize(BLOCK, 0);
        file.read_exact(&mut buffer)?;
        hash.update(&buffer);
    }
    Ok(hash.finalize().into())
}

#[derive(Clone, Copy)]
struct State {
    position: u64,
    cursor: u64,
    count: u64,
    output_len: u64,
    digest: [u8; 32],
}

struct HashedFile {
    file: File,
    hash: Sha256,
}
impl Write for HashedFile {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let written = self.file.write(bytes)?;
        self.hash.update(&bytes[..written]);
        Ok(written)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.file.flush()
    }
}
impl Seek for HashedFile {
    fn seek(&mut self, pos: SeekFrom) -> io::Result<u64> {
        self.file.seek(pos)
    }
}

fn hash_prefix(file: &mut File, size: u64) -> io::Result<Sha256> {
    file.seek(SeekFrom::Start(0))?;
    let mut source = file.take(size);
    let mut hash = Sha256::new();
    let mut buf = [0u8; BLOCK];
    let mut read = 0u64;
    loop {
        let n = source.read(&mut buf)?;
        if n == 0 {
            break;
        }
        read += n as u64;
        hash.update(&buf[..n]);
    }
    if read != size {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "Partial index is shorter than checkpoint",
        ));
    }
    Ok(hash)
}

fn save_state(path: &Path, identity: &[u8; 32], state: State) -> io::Result<()> {
    let mut tmp_name = path.as_os_str().to_owned();
    let nonce = std::time::SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    tmp_name.push(format!(".tmp-{}-{nonce}", std::process::id()));
    let tmp = PathBuf::from(tmp_name);
    let mut created = false;
    let result = (|| {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp)?;
        created = true;
        file.write_all(MAGIC)?;
        file.write_all(identity)?;
        for value in [state.position, state.cursor, state.count, state.output_len] {
            file.write_all(&value.to_le_bytes())?;
        }
        file.write_all(&state.digest)?;
        file.sync_all()?;
        fs::rename(&tmp, path)
    })();
    if result.is_err() && created {
        let _ = fs::remove_file(tmp);
    }
    result
}

fn read_state(path: &Path, identity: &[u8; 32]) -> io::Result<State> {
    let mut file = File::open(path)?;
    let mut bytes = [0u8; 104];
    file.read_exact(&mut bytes)?;
    if file.metadata()?.len() != bytes.len() as u64
        || &bytes[..8] != MAGIC
        || &bytes[8..40] != identity
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Checkpoint does not match this archive",
        ));
    }
    let word = |start| u64::from_le_bytes(bytes[start..start + 8].try_into().unwrap());
    Ok(State {
        position: word(40),
        cursor: word(48),
        count: word(56),
        output_len: word(64),
        digest: bytes[72..104].try_into().unwrap(),
    })
}

fn checkpoint(
    output: &mut BufWriter<HashedFile>,
    path: &Path,
    identity: &[u8; 32],
    state: &mut State,
) -> io::Result<()> {
    output.flush()?;
    output.get_ref().file.sync_data()?;
    state.output_len = output.stream_position()?;
    state.digest = output.get_ref().hash.clone().finalize().into();
    save_state(path, identity, *state)
}

/// Create or continue an index using adjacent `.partial` and `.checkpoint` files.
/// A sampled source fingerprint detects common changes; it is not a whole-file hash.
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
    let partial = sibling(path, ".partial");
    let state_path = sibling(path, ".checkpoint");
    let lock_path = sibling(path, ".lock");
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(lock_path)?;
    lock.try_lock().map_err(|_| {
        io::Error::new(
            io::ErrorKind::WouldBlock,
            "Index is in use by another process",
        )
    })?;
    if path.exists() {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "Final index already exists",
        ));
    }
    let identity = fingerprint(archive)?;
    let (file, hash, mut state) = if state_path.exists() {
        let state = read_state(&state_path, &identity)?;
        if state.cursor < front || state.cursor > state.position || state.position > end {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Invalid checkpoint offsets",
            ));
        }
        let mut file = OpenOptions::new().read(true).write(true).open(&partial)?;
        if file.metadata()?.len() < state.output_len {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Partial index is shorter than checkpoint",
            ));
        }
        let hash = hash_prefix(&mut file, state.output_len)?;
        let actual: [u8; 32] = hash.clone().finalize().into();
        if actual != state.digest {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Partial index does not match checkpoint",
            ));
        }
        file.set_len(state.output_len)?;
        file.seek(SeekFrom::Start(state.output_len))?;
        (file, hash, state)
    } else {
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&partial)?;
        let init = (|| {
            writeln!(
                file,
                "kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\ttext_prefix"
            )?;
            writeln!(file, "front\t0x0\t0x{front:x}\t{front}\t\t")?;
            file.sync_data()?;
            let output_len = file.stream_position()?;
            let hash = hash_prefix(&mut file, output_len)?;
            file.seek(SeekFrom::Start(output_len))?;
            let state = State {
                position: front,
                cursor: front,
                count: 0,
                output_len,
                digest: hash.clone().finalize().into(),
            };
            save_state(&state_path, &identity, state)?;
            Ok((hash, state))
        })();
        match init {
            Ok((hash, state)) => (file, hash, state),
            Err(error) => {
                drop(file);
                let _ = fs::remove_file(&partial);
                return Err(error);
            }
        }
    };
    let mut output = BufWriter::new(HashedFile { file, hash });
    let mut source = File::open(&archive.path)?;
    let mut buffer = [0u8; BLOCK];
    let mut last_checkpoint = Instant::now();
    while state.position < end {
        progress.store(state.position, Ordering::Relaxed);
        if cancel.load(Ordering::Relaxed) {
            checkpoint(&mut output, &state_path, &identity, &mut state)?;
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Indexing paused; resume using the same destination",
            ));
        }
        if last_checkpoint.elapsed() >= Duration::from_secs(5) {
            checkpoint(&mut output, &state_path, &identity, &mut state)?;
            last_checkpoint = Instant::now();
        }
        source.seek(SeekFrom::Start(state.position))?;
        let n = source.read(&mut buffer[..(end - state.position).min(BLOCK as u64) as usize])?;
        if n == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "Archive changed during indexing",
            ));
        }
        let mut found = None;
        for (i, byte) in buffer[..n].iter().enumerate() {
            let offset = state.position + i as u64;
            if offset % 16 != 0 || *byte != 0x78 {
                continue;
            }
            match indexer::zlib_end(&mut source, offset, end, &cancel) {
                Ok(Some(stream)) => {
                    found = Some((offset, stream));
                    break;
                }
                Ok(None) => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {
                    checkpoint(&mut output, &state_path, &identity, &mut state)?;
                    return Err(io::Error::new(
                        io::ErrorKind::Interrupted,
                        "Indexing paused; resume using the same destination",
                    ));
                }
                Err(error) => return Err(error),
            }
        }
        if let Some((start, (stream_end, decoded, label))) = found {
            if state.cursor < start {
                writeln!(
                    output,
                    "unclassified\t0x{:x}\t0x{start:x}\t{}\t\t",
                    state.cursor,
                    start - state.cursor
                )?;
            }
            writeln!(
                output,
                "zlib\t0x{start:x}\t0x{stream_end:x}\t{}\t{decoded}\t0x{start:x}\t{label}",
                stream_end - start
            )?;
            state.cursor = stream_end;
            state.position = stream_end;
            state.count += 1;
        } else {
            state.position += n as u64;
        }
    }
    if fingerprint(archive)? != identity {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Archive changed during indexing",
        ));
    }
    if state.cursor < end {
        writeln!(
            output,
            "unclassified\t0x{:x}\t0x{end:x}\t{}\t\t",
            state.cursor,
            end - state.cursor
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
    output.get_ref().file.sync_all()?;
    drop(output);
    fs::hard_link(&partial, path)?;
    let _ = fs::remove_file(&partial);
    let _ = fs::remove_file(&state_path);
    Ok(state.count)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resumes_partial_and_rejects_corruption() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../story000_bvh4.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let directory = std::env::temp_dir().join(format!("annoyed-resume-{}", std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let expected = directory.join("expected.tsv");
        indexer::create(
            &archive,
            &expected,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        let complete = fs::read(&expected).unwrap();
        let partial_end = complete
            .iter()
            .enumerate()
            .filter(|(_, b)| **b == b'\n')
            .nth(2)
            .unwrap()
            .0
            + 1;
        let target = directory.join("resumed.tsv");
        let part = sibling(&target, ".partial");
        fs::write(&part, &complete[..partial_end]).unwrap();
        let mut hash = Sha256::new();
        hash.update(&complete[..partial_end]);
        let state = State {
            position: 0x4f1,
            cursor: 0x4f1,
            count: 1,
            output_len: partial_end as u64,
            digest: hash.finalize().into(),
        };
        save_state(
            &sibling(&target, ".checkpoint"),
            &fingerprint(&archive).unwrap(),
            state,
        )
        .unwrap();
        assert_eq!(
            create(
                &archive,
                &target,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap(),
            4
        );
        assert_eq!(fs::read(&target).unwrap(), complete);
        assert!(!part.exists());
        let cancelled = directory.join("paused.tsv");
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
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .open(sibling(&cancelled, ".lock"))
            .unwrap();
        lock.try_lock().unwrap();
        assert_eq!(
            create(
                &archive,
                &cancelled,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::WouldBlock
        );
        drop(lock);
        let damaged = sibling(&cancelled, ".partial");
        let mut file = OpenOptions::new().write(true).open(&damaged).unwrap();
        file.write_all(b"X").unwrap();
        drop(file);
        assert_eq!(
            create(
                &archive,
                &cancelled,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::InvalidData
        );
        assert!(!cancelled.exists());
        let copied = directory.join("copy.rpf");
        fs::copy(&source, &copied).unwrap();
        let copy_archive = Archive::open(&copied).unwrap();
        let changed = directory.join("changed.tsv");
        assert_eq!(
            create(
                &copy_archive,
                &changed,
                Arc::new(AtomicBool::new(true)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::Interrupted
        );
        let mut file = OpenOptions::new().write(true).open(&copied).unwrap();
        file.seek(SeekFrom::Start(200)).unwrap();
        file.write_all(b"changed").unwrap();
        drop(file);
        assert_eq!(
            create(
                &copy_archive,
                &changed,
                Arc::new(AtomicBool::new(false)),
                Arc::new(AtomicU64::new(0))
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::InvalidData
        );
        assert!(!changed.exists());
        fs::remove_dir_all(directory).unwrap();
    }
}
