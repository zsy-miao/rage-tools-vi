use flate2::{Decompress, FlushDecompress, Status};
use std::env;
use std::error::Error;
use std::fs::{self, OpenOptions};
use std::io::{self, BufWriter, Write};
use std::ops::Range;

mod pack_report;
mod partition;
mod range_extract;
mod range_map;

const RPF9_MAGIC: &[u8] = b"9FPR";
const PAGE_SIZE: usize = 4096;
const STREAM_ALIGNMENT: usize = 16;
const ZLIB_CHUNK_SIZE: usize = 0x10000;
const MAX_PAYLOAD_SIZE: usize = 16 * 1024 * 1024;
const USAGE: &str = "Usage:
  rage-tools-vi inspect <archive>
  rage-tools-vi list <archive>
  rage-tools-vi map <archive> [<hex-start> <hex-end>]
  rage-tools-vi packs <archive> [<hex-start> <hex-end>]
  rage-tools-vi partition <archive> [<hex-start> <hex-end>]
  rage-tools-vi sections <archive> <hex-offset>
  rage-tools-vi extract <archive> <hex-offset> <output>
  rage-tools-vi extract-zlib <archive> <hex-start> <hex-end> <output>
  rage-tools-vi extract-raw <archive> <hex-start> <hex-end> <output>

List locates PSIN zlib streams. Sections and extract can join a validated continuation.
Packs reports header fields and metadata entropy. Embedded trailers need explicit pack bounds.
Range extraction uses an exclusive end offset.
Partition reports candidate object and byte ranges against header word +0x24.";

fn main() {
    if let Err(error) = run(env::args_os().skip(1).collect()) {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run(args: Vec<std::ffi::OsString>) -> Result<(), Box<dyn Error>> {
    if matches!(args.as_slice(), [help] if help == "--help" || help == "-h") {
        println!("{USAGE}");
        return Ok(());
    }

    let (command, path) = match args.as_slice() {
        [command, path]
            if ["inspect", "list", "map", "packs", "partition"]
                .iter()
                .any(|name| command == *name) =>
        {
            (command, path)
        }
        [command, path, _, _]
            if command == "map" || command == "packs" || command == "partition" =>
        {
            (command, path)
        }
        [command, path, _] if command == "sections" => (command, path),
        [command, path, _, _] if command == "extract" => (command, path),
        [command, path, _, _, _] if command == "extract-zlib" || command == "extract-raw" => {
            (command, path)
        }
        _ => return Err(USAGE.into()),
    };
    let data = fs::read(path)?;
    if !data.starts_with(RPF9_MAGIC) {
        return Err("expected a little-endian RPF9 signature at byte zero".into());
    }

    let stdout = io::stdout().lock();
    let mut output = BufWriter::new(stdout);

    if command == "inspect" {
        writeln!(output, "archive_bytes\t{}", data.len())?;
        writeln!(output, "header_offset\theader_span\tword_08\tword_0c\tword_24")?;
        for offset in (0..data.len()).step_by(PAGE_SIZE) {
            let tail = &data[offset..];
            if tail.len() < 0x40 || !tail.starts_with(RPF9_MAGIC) {
                continue;
            }
            let span = word(tail, 4) as usize;
            if !(0x40..=tail.len()).contains(&span) {
                continue;
            }
            writeln!(
                output,
                "0x{offset:x}\t0x{span:x}\t0x{:x}\t0x{:x}\t{}",
                word(tail, 8),
                word(tail, 12),
                word(tail, 0x24),
            )?;
        }
    } else if command == "map" || command == "packs" || command == "partition" {
        let range = match args.get(2..4) {
            Some([start, end]) => parse_offset(start)?..parse_offset(end)?,
            _ => 0..data.len(),
        };
        match command.to_str() {
            Some("map") => range_map::write_map(&mut output, &data, range)?,
            Some("packs") => pack_report::write_packs(&mut output, &data, range)?,
            _ => partition::write_partition(&mut output, &data, range)?,
        }
    } else if command == "extract-zlib" || command == "extract-raw" {
        let start = parse_offset(&args[2])?;
        let end = parse_offset(&args[3])?;
        let input = data
            .get(start..end)
            .filter(|bytes| !bytes.is_empty())
            .ok_or("expected a nonempty byte range inside the archive")?;
        if command == "extract-raw" {
            write_new_file(&args[4], input)?;
            writeln!(output, "0x{start:x}..0x{end:x}: {} raw bytes", input.len())?;
        } else {
            let (decoded, streams) = range_extract::decode_chain(input, start)?;
            write_new_file(&args[4], &decoded)?;
            writeln!(
                output,
                "0x{start:x}..0x{end:x}: {streams} zlib streams -> {} decoded bytes",
                decoded.len()
            )?;
        }
    } else if command == "list" {
        writeln!(output, "offset\tstored_bytes\tdecoded_bytes\tmagic")?;
        let mut next_offset = 0;
        for (index, input) in data.chunks(STREAM_ALIGNMENT).enumerate() {
            let offset = index * STREAM_ALIGNMENT;
            if offset < next_offset || !is_zlib_header(input) {
                continue;
            }
            if let Some((stored, decoded)) = decode_psin(&data[offset..]) {
                writeln!(output, "0x{offset:x}\t{stored}\t{}\tPSIN", decoded.len())?;
                next_offset = offset + stored;
            }
        }
    } else {
        let offset = parse_offset(&args[2])?;
        if offset % STREAM_ALIGNMENT != 0 {
            return Err("offset must be 16-byte aligned".into());
        }
        let input = data.get(offset..).ok_or("offset is outside the archive")?;
        let (stored, mut decoded) = decode_psin(input)
            .ok_or("no complete PSIN zlib stream within the scan limits at this offset")?;
        let stored = stored + append_psin_continuation(input, stored, &mut decoded);
        if command == "sections" {
            let sections = psin_sections(&decoded).ok_or("incomplete or invalid PSIN sections")?;
            writeln!(output, "tag\tdecoded_offset\tsection_bytes")?;
            for (tag, range) in sections {
                writeln!(output, "{tag}\t0x{:x}\t{}", range.start, range.len())?;
            }
            output.flush()?;
            return Ok(());
        }
        write_new_file(&args[3], &decoded)?;
        writeln!(
            output,
            "0x{offset:x}: {stored} stored bytes -> {} PSIN bytes",
            decoded.len()
        )?;
    }
    output.flush()?;
    Ok(())
}

fn write_new_file(path: &std::ffi::OsStr, data: &[u8]) -> io::Result<()> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?
        .write_all(data)
}

fn parse_offset(value: &std::ffi::OsStr) -> Result<usize, Box<dyn Error>> {
    let text = value.to_str().ok_or("expected a hexadecimal offset")?;
    Ok(usize::from_str_radix(text.trim_start_matches("0x"), 16)?)
}

fn word(header: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(header[offset..offset + 4].try_into().unwrap())
}

fn is_zlib_header(input: &[u8]) -> bool {
    matches!(input, [0x78, 0x01 | 0x5e | 0x9c | 0xda, ..])
}

fn psin_sections(data: &[u8]) -> Option<Vec<(&str, Range<usize>)>> {
    let mut sections = Vec::new();
    let mut offset = 0;
    while offset < data.len() {
        let header = data.get(offset..offset + 8)?;
        let tag = std::str::from_utf8(&header[..4]).ok()?;
        let size = u32::from_be_bytes(header[4..].try_into().unwrap()) as usize;
        if !tag.bytes().all(|byte| byte.is_ascii_uppercase()) || size < 8 {
            return None;
        }
        let end = offset.checked_add(size)?;
        if end > data.len() {
            return None;
        }
        sections.push((tag, offset..end));
        offset = end;
    }
    Some(sections)
}

fn append_psin_continuation(input: &[u8], stored: usize, decoded: &mut Vec<u8>) -> usize {
    let first_size = decoded.len();
    if first_size != ZLIB_CHUNK_SIZE || psin_sections(decoded).is_some() {
        return 0;
    }
    // The observed split records continue at the next 16-byte boundary.
    let next = stored.next_multiple_of(STREAM_ALIGNMENT);
    let Some((padding, tail)) = input
        .get(stored..)
        .and_then(|bytes| bytes.split_at_checked(next - stored))
    else {
        return 0;
    };
    if padding.iter().any(|&byte| byte != 0) {
        return 0;
    }
    let Some((consumed, continuation)) = decode_zlib(tail, &[]) else {
        return 0;
    };
    if continuation.starts_with(b"PSIN") || first_size + continuation.len() > MAX_PAYLOAD_SIZE {
        return 0;
    }
    decoded.extend(continuation);
    if let Some(sections) = psin_sections(decoded) {
        if let Some(("CHKS", range)) = sections.last() {
            let checksum = &decoded[range.clone()];
            if checksum.len() >= 12
                && u32::from_be_bytes(checksum[8..12].try_into().unwrap()) as usize == decoded.len()
            {
                return consumed;
            }
        }
    }
    decoded.truncate(first_size);
    0
}

fn decode_psin(input: &[u8]) -> Option<(usize, Vec<u8>)> {
    decode_zlib(input, b"PSIN")
}

/// Require stream end so the zlib Adler-32 is checked before accepting a payload.
fn decode_zlib(input: &[u8], prefix: &[u8]) -> Option<(usize, Vec<u8>)> {
    if !is_zlib_header(input) {
        return None;
    }
    let mut decoder = Decompress::new(true);
    let mut buffer = [0; 8192];
    let mut decoded = Vec::new();
    loop {
        let read = decoder.total_in() as usize;
        let written = decoder.total_out() as usize;
        let status = decoder
            .decompress(&input[read..], &mut buffer, FlushDecompress::None)
            .ok()?;
        let produced = decoder.total_out() as usize - written;
        decoded.extend_from_slice(&buffer[..produced]);
        if decoded.len() > MAX_PAYLOAD_SIZE
            || (decoded.len() >= prefix.len() && !decoded.starts_with(prefix))
        {
            return None;
        }
        if status == Status::StreamEnd {
            return decoded
                .starts_with(prefix)
                .then_some((decoder.total_in() as usize, decoded));
        }
        if produced == 0 && decoder.total_in() as usize == read {
            return None;
        }
    }
}
