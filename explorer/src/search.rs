//! Streaming exact byte search across decoded zlib data.
use crate::{archive::Archive, index};
use std::io::{self, Write};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

pub fn page(
    archive: &Archive,
    path: &Path,
    mut position: u64,
    query: &[u8],
    cancel: Arc<AtomicBool>,
) -> io::Result<index::Page> {
    if query.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Search text is empty",
        ));
    }
    index::check_archive_size(path, archive.size)?;
    let mut archive_reader = archive.reader()?;
    let mut rows = Vec::new();
    let mut examined = 0;
    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Search cancelled",
            ));
        }
        let page = index::page(path, position, "")?;
        examined += page.rows.len();
        for range in page.rows {
            if cancel.load(Ordering::Relaxed) {
                return Err(io::Error::new(
                    io::ErrorKind::Interrupted,
                    "Search cancelled",
                ));
            }
            if range.kind == "zlib" || range.kind == "raw_deflate" {
                let mut matcher = Matcher::new(query)?.with_cancel(cancel.clone());
                if range.kind == "raw_deflate" {
                    archive_reader.decode_deflate_into(range.start, range.end, &mut matcher)?;
                } else {
                    archive_reader.decode_zlib_into(range.start, range.end, &mut matcher)?;
                }
                if matcher.found() {
                    rows.push(range);
                }
            }
        }
        match page.next {
            Some(next) if rows.len() < index::PAGE_ROWS && examined < 4096 => position = next,
            next => return Ok(index::Page { rows, next }),
        }
    }
}

pub struct Matcher {
    pattern: Vec<u8>,
    fallback: Vec<usize>,
    matched: usize,
    found: bool,
    cancel: Option<Arc<AtomicBool>>,
}

impl Matcher {
    pub fn new(pattern: &[u8]) -> io::Result<Self> {
        if pattern.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Search text is empty",
            ));
        }
        let mut fallback = vec![0; pattern.len()];
        let mut matched = 0;
        for i in 1..pattern.len() {
            while matched > 0 && pattern[i] != pattern[matched] {
                matched = fallback[matched - 1];
            }
            if pattern[i] == pattern[matched] {
                matched += 1;
            }
            fallback[i] = matched;
        }
        Ok(Self {
            pattern: pattern.to_vec(),
            fallback,
            matched: 0,
            found: false,
            cancel: None,
        })
    }
    pub fn with_cancel(mut self, cancel: Arc<AtomicBool>) -> Self {
        self.cancel = Some(cancel);
        self
    }
    pub fn found(&self) -> bool {
        self.found
    }
}

impl Write for Matcher {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self
            .cancel
            .as_ref()
            .is_some_and(|cancel| cancel.load(Ordering::Relaxed))
        {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "Search cancelled",
            ));
        }
        if !self.found {
            for &byte in data {
                while self.matched > 0 && byte != self.pattern[self.matched] {
                    self.matched = self.fallback[self.matched - 1];
                }
                if byte == self.pattern[self.matched] {
                    self.matched += 1;
                }
                if self.matched == self.pattern.len() {
                    self.found = true;
                    break;
                }
            }
        }
        Ok(data.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matches_across_chunks_and_overlapping_prefixes() {
        let mut matcher = Matcher::new(b"ababac").unwrap();
        matcher.write_all(b"zzababa").unwrap();
        assert!(!matcher.found());
        matcher.write_all(b"baczz").unwrap();
        assert!(matcher.found());
        assert!(Matcher::new(b"").is_err());
    }

    #[test]
    fn searches_decoded_control_and_cancels() {
        use std::sync::atomic::AtomicU64;
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../story000_bvh4.rpf");
        if !source.exists() {
            return;
        }
        let archive = Archive::open(&source).unwrap();
        let directory = std::env::temp_dir().join(format!("annoyed-search-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let index_path = directory.join("index.tsv");
        crate::indexer::create(
            &archive,
            &index_path,
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
        )
        .unwrap();
        let matches = page(
            &archive,
            &index_path,
            0,
            b"story000_terrain_bvh",
            Arc::new(AtomicBool::new(false)),
        )
        .unwrap();
        assert!(matches.rows.iter().any(|range| range.start == 0x1000));
        let error = page(
            &archive,
            &index_path,
            0,
            b"terrain",
            Arc::new(AtomicBool::new(true)),
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::Interrupted);
        std::fs::remove_dir_all(directory).unwrap();
    }
}
