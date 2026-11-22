use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Seek, SeekFrom};
use std::path::Path;

pub const PAGE_ROWS: usize = 40;
const MAX_LINE: u64 = 65536;

#[derive(Clone, Debug)]
pub struct Range {
    pub kind: String,
    pub start: u64,
    pub end: u64,
    pub decoded: String,
    pub text_prefix: String,
}

#[derive(Debug, Clone)]
pub struct Page {
    pub rows: Vec<Range>,
    pub next: Option<u64>,
}

fn number(value: &str) -> io::Result<u64> {
    let value = value.trim();
    let parsed = if let Some(hex) = value.strip_prefix("0x") {
        u64::from_str_radix(hex, 16)
    } else {
        value.parse()
    };
    parsed.map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid index offset"))
}

pub fn check_archive_size(path: &Path, archive_size: u64) -> io::Result<()> {
    let mut file = File::open(path)?;
    let len = file.metadata()?.len();
    let start = len.saturating_sub(MAX_LINE);
    file.seek(SeekFrom::Start(start))?;
    let mut tail = Vec::new();
    file.read_to_end(&mut tail)?;
    let end_pos = tail
        .iter()
        .rposition(|&b| b != b'\n' && b != b'\r')
        .map(|i| i + 1)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Empty index"))?;
    let begin = tail[..end_pos]
        .iter()
        .rposition(|&b| b == b'\n')
        .map(|i| i + 1);
    if start > 0 && begin.is_none() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Index line too long",
        ));
    }
    let last = std::str::from_utf8(&tail[begin.unwrap_or(0)..end_pos])
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Index is not UTF-8"))?;
    let end = last
        .split('\t')
        .nth(2)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Malformed final index row"))?;
    if number(end)? != archive_size {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Index coverage does not match archive size",
        ));
    }
    Ok(())
}

/// Find the first indexed row whose end exceeds an archive-relative offset.
/// The index must be ordered by non-overlapping ranges, as produced here.
pub fn seek_offset(path: &Path, target: u64) -> io::Result<u64> {
    let mut file = File::open(path)?;
    let len = file.metadata()?.len();
    let mut reader = BufReader::new(file.try_clone()?);
    let mut header = String::new();
    reader.by_ref().take(MAX_LINE).read_line(&mut header)?;
    if header.split('\t').take(3).collect::<Vec<_>>() != ["kind", "start", "end"] {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid index header",
        ));
    }
    let mut low = reader.stream_position()?;
    let mut high = len;
    while low < high {
        let mid = low + (high - low) / 2;
        let window_start = mid.saturating_sub(MAX_LINE).max(low);
        file.seek(SeekFrom::Start(window_start))?;
        let mut prefix = vec![0u8; (mid - window_start) as usize];
        file.read_exact(&mut prefix)?;
        let row_start = match prefix.iter().rposition(|&b| b == b'\n') {
            Some(i) => window_start + i as u64 + 1,
            None if window_start == low => low,
            None => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "Index line too long",
                ))
            }
        };
        reader.seek(SeekFrom::Start(row_start))?;
        let mut row = String::new();
        let n = reader.by_ref().take(MAX_LINE).read_line(&mut row)?;
        if n == 0 || (n as u64 == MAX_LINE && !row.ends_with('\n')) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Invalid index row",
            ));
        }
        let end = row
            .split('\t')
            .nth(2)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Malformed index row"))?;
        if number(end)? <= target {
            low = reader.stream_position()?;
        } else {
            high = row_start;
        }
    }
    Ok(low)
}

pub fn page(path: &Path, position: u64, query: &str) -> io::Result<Page> {
    page_until(path, position, query, None)
}

/// Read a page and stop before a range that starts at or after `end`.
pub fn page_until(
    path: &Path,
    position: u64,
    query: &str,
    end_limit: Option<u64>,
) -> io::Result<Page> {
    let mut reader = BufReader::new(File::open(path)?);
    reader.seek(SeekFrom::Start(position))?;
    let mut rows = Vec::new();
    if position == 0 {
        let mut header = String::new();
        reader.by_ref().take(MAX_LINE).read_line(&mut header)?;
        let columns: Vec<_> = header.trim_end().split('\t').collect();
        if columns.get(0..3) != Some(&["kind", "start", "end"][..]) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Expected kind, start, end index columns",
            ));
        }
    }
    let mut examined = 0;
    let query = query.to_ascii_lowercase();
    while rows.len() < PAGE_ROWS && examined < 4096 {
        let mut line = String::new();
        let n = reader.by_ref().take(MAX_LINE).read_line(&mut line)?;
        if n == 0 {
            return Ok(Page { rows, next: None });
        }
        examined += 1;
        if !line.ends_with('\n') && n as u64 == MAX_LINE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Index line too long",
            ));
        }
        let fields: Vec<_> = line.trim_end_matches(['\r', '\n']).split('\t').collect();
        if fields.len() < 3 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "Malformed index row",
            ));
        }
        let start = number(fields[1])?;
        let end = number(fields[2])?;
        if end <= start {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "Invalid range"));
        }
        if let Some(stored) = fields.get(3).filter(|value| !value.is_empty()) {
            let stored: u64 = stored
                .parse()
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid stored size"))?;
            if stored != end - start {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "Stored size does not match range",
                ));
            }
        }
        if end_limit.is_some_and(|limit| start >= limit) {
            return Ok(Page { rows, next: None });
        }
        if !query.is_empty() && !line.to_ascii_lowercase().contains(&query) {
            continue;
        }
        rows.push(Range {
            kind: fields[0].to_owned(),
            start,
            end,
            decoded: fields.get(4).unwrap_or(&"").to_string(),
            text_prefix: fields.get(6).unwrap_or(&"").chars().take(512).collect(),
        });
    }
    let position = reader.stream_position()?;
    let next = if reader.fill_buf()?.is_empty() {
        None
    } else {
        Some(position)
    };
    Ok(Page { rows, next })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[test]
    fn pages_large_offsets_without_reloading_the_index() {
        let path = std::env::temp_dir().join(format!("annoyed-index-{}", std::process::id()));
        let mut file = File::create(&path).unwrap();
        writeln!(file, "kind\tstart\tend\tstored_bytes\tdecoded_bytes").unwrap();
        for i in 0..83u64 {
            let start = (1u64 << 50) + i * 16;
            writeln!(file, "zlib\t0x{start:x}\t0x{:x}\t16\t100", start + 16).unwrap();
        }
        drop(file);
        let first = page(&path, 0, "").unwrap();
        assert_eq!(first.rows.len(), 40);
        assert_eq!(first.rows[0].start, 1u64 << 50);
        let second = page(&path, first.next.unwrap(), "").unwrap();
        assert_eq!(second.rows.len(), 40);
        let third = page(&path, second.next.unwrap(), "").unwrap();
        assert_eq!(third.rows.len(), 3);
        assert!(third.next.is_none());
        let cutoff = (1u64 << 50) + 17 * 16;
        let bounded = page_until(&path, 0, "", Some(cutoff)).unwrap();
        assert_eq!(bounded.rows.len(), 17);
        assert!(bounded.next.is_none());
        assert!(page(&path, 0, "not present").unwrap().rows.is_empty());
        assert!(check_archive_size(&path, 1).is_err());
        assert!(check_archive_size(&path, (1u64 << 50) + 83 * 16).is_ok());
        for i in 0..83u64 {
            let offset = (1u64 << 50) + i * 16;
            let position = seek_offset(&path, offset).unwrap();
            assert_eq!(page(&path, position, "").unwrap().rows[0].start, offset);
            let position = seek_offset(&path, offset + 15).unwrap();
            assert_eq!(page(&path, position, "").unwrap().rows[0].start, offset);
        }
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    #[ignore = "uses the local anim stream index"]
    fn seek_real_large_index() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../output/index/anim.tsv");
        for target in [0, 1, 0x10000, 0x100000000, 4407626383] {
            let position = seek_offset(&path, target).unwrap();
            let first = page(&path, position, "").unwrap().rows.remove(0);
            assert!(
                first.start <= target && target < first.end,
                "{target:x}: {first:?}"
            );
        }
    }
}
