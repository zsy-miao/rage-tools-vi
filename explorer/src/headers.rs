//! Bounded scans for plausible page-aligned RPF9 headers.
use crate::archive::Archive;
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom};

const PAGE: u64 = 4096;
const BLOCK: usize = 65536;
const BATCH: u64 = 64 * 1024 * 1024;

#[derive(Clone, Debug)]
pub struct Header {
    pub offset: u64,
    pub front_bytes: u32,
    pub trailer_bytes: u32,
    pub declared_entries: u32,
}

#[derive(Clone, Debug)]
pub struct Page {
    pub headers: Vec<Header>,
    pub next: Option<u64>,
}

pub fn scan(archive: &Archive, start: u64) -> io::Result<Page> {
    let mut file = File::open(&archive.path)?;
    let mut offset = start
        .checked_add(PAGE - 1)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "Offset too large"))?
        / PAGE
        * PAGE;
    let limit = archive.size.min(offset.saturating_add(BATCH));
    let mut headers = Vec::new();
    let mut buffer = [0u8; BLOCK];
    while offset < limit {
        file.seek(SeekFrom::Start(offset))?;
        let n = (archive.size - offset).min(BLOCK as u64) as usize;
        file.read_exact(&mut buffer[..n])?;
        let mut i = 0usize;
        while i + 96 <= n && offset + (i as u64) < limit {
            let at = offset + i as u64;
            if &buffer[i..i + 4] == b"9FPR" {
                let word =
                    |n: usize| u32::from_le_bytes(buffer[i + n..i + n + 4].try_into().unwrap());
                let front = word(4);
                if front >= 0x40 && u64::from(front) <= archive.size - at {
                    headers.push(Header {
                        offset: at,
                        front_bytes: front,
                        trailer_bytes: word(12),
                        declared_entries: word(0x24),
                    });
                    if headers.len() == 40 {
                        let next = at.saturating_add(PAGE);
                        return Ok(Page {
                            headers,
                            next: (next < archive.size).then_some(next),
                        });
                    }
                }
            }
            i += PAGE as usize;
        }
        offset = offset.saturating_add(BLOCK as u64);
    }
    Ok(Page {
        headers,
        next: (offset < archive.size).then_some(offset),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;
    #[test]
    fn finds_control_root_and_embedded_header() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../core_licenses_data.rpf");
        if !path.exists() {
            return;
        }
        let archive = Archive::open(&path).unwrap();
        let page = scan(&archive, 0).unwrap();
        assert!(page.headers.iter().any(|h| h.offset == 0));
        assert!(page.headers.iter().any(|h| h.offset == 0x1000));
        assert!(page.next.is_none());
    }

    #[test]
    #[ignore = "scans the local data.rpf corpus"]
    fn scans_local_data() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../data.rpf");
        let archive = Archive::open(&path).unwrap();
        let mut position = 0;
        let mut count = 0;
        loop {
            let page = scan(&archive, position).unwrap();
            count += page.headers.len();
            match page.next {
                Some(next) => position = next,
                None => break,
            }
        }
        assert_eq!(count, 42);
    }
}
