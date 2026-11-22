use super::{decode_zlib, is_zlib_header, word, RPF9_MAGIC, STREAM_ALIGNMENT, ZLIB_CHUNK_SIZE};
use std::error::Error;
use std::io::{self, Write};
use std::ops::Range;

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum SpanKind {
    ZeroRun,
    Unclassified,
    Zlib,
}

impl SpanKind {
    fn label(self) -> &'static str {
        match self {
            SpanKind::ZeroRun => "zero_run",
            SpanKind::Unclassified => "unclassified",
            SpanKind::Zlib => "zlib",
        }
    }
}

pub(super) struct Span {
    pub kind: SpanKind,
    pub range: Range<usize>,
    pub decoded: usize,
    pub chain_start: usize,
}

pub(super) fn payload_range(
    data: &[u8],
    pack_range: Range<usize>,
) -> Result<Range<usize>, Box<dyn Error>> {
    let pack = data.get(pack_range.clone()).ok_or("invalid pack byte range")?;
    if pack.len() < 0x40 || !pack.starts_with(RPF9_MAGIC) {
        return Err("pack range must begin with an RPF9 header".into());
    }

    let front_end = word(pack, 4) as usize;
    let trailer_size = word(pack, 12) as usize;
    let trailer_start = pack
        .len()
        .checked_sub(trailer_size)
        .ok_or("trailer span exceeds pack range")?;
    if front_end < 0x40 || front_end > trailer_start {
        return Err("invalid front metadata span".into());
    }

    Ok(pack_range.start + front_end..pack_range.start + trailer_start)
}

/// Account for every byte in a payload range.
pub(super) fn scan_payload(data: &[u8], payload: Range<usize>) -> Vec<Span> {
    let (start, stop) = (payload.start, payload.end);
    let mut spans = Vec::new();
    let mut cursor = start;
    let mut previous_size = 0;
    let mut chain_start = start;
    for offset in (start.next_multiple_of(STREAM_ALIGNMENT)..stop).step_by(STREAM_ALIGNMENT) {
        if offset < cursor || !is_zlib_header(&data[offset..stop]) {
            continue;
        }
        let Some((stored, decoded)) = decode_zlib(&data[offset..stop], &[]) else {
            continue;
        };
        // A full-size chunk can continue at the next aligned offset across zero bytes.
        if previous_size != ZLIB_CHUNK_SIZE
            || offset != cursor.next_multiple_of(STREAM_ALIGNMENT)
            || data[cursor..offset].iter().any(|&byte| byte != 0)
        {
            chain_start = offset;
        }
        push_gaps(&mut spans, data, cursor..offset);
        cursor = offset + stored;
        previous_size = decoded.len();
        spans.push(Span {
            kind: SpanKind::Zlib,
            range: offset..cursor,
            decoded: previous_size,
            chain_start,
        });
    }
    push_gaps(&mut spans, data, cursor..stop);
    spans
}

pub(super) fn write_map(
    output: &mut impl Write,
    data: &[u8],
    pack_range: Range<usize>,
) -> Result<(), Box<dyn Error>> {
    let payload = payload_range(data, pack_range.clone())?;
    writeln!(output, "kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start")?;
    write_span(output, "front", pack_range.start, payload.start)?;
    for span in scan_payload(data, payload.clone()) {
        match span.kind {
            SpanKind::Zlib => writeln!(
                output,
                "zlib\t0x{:x}\t0x{:x}\t{}\t{}\t0x{:x}",
                span.range.start, span.range.end, span.range.len(), span.decoded, span.chain_start
            )?,
            kind => write_span(output, kind.label(), span.range.start, span.range.end)?,
        }
    }
    if payload.end < pack_range.end {
        write_span(output, "trailer", payload.end, pack_range.end)?;
    }
    Ok(())
}

fn push_gaps(spans: &mut Vec<Span>, data: &[u8], range: Range<usize>) {
    let mut start = range.start;
    let mut cursor = start;
    while cursor < range.end {
        if data[cursor] != 0 {
            cursor += 1;
            continue;
        }
        let zero_start = cursor;
        while cursor < range.end && data[cursor] == 0 {
            cursor += 1;
        }
        // Report short gaps between known spans, and longer runs that end at alignment.
        if (zero_start == start || cursor - zero_start >= STREAM_ALIGNMENT)
            && (cursor == range.end || cursor % STREAM_ALIGNMENT == 0)
        {
            if start < zero_start {
                push_span(spans, SpanKind::Unclassified, start, zero_start);
            }
            push_span(spans, SpanKind::ZeroRun, zero_start, cursor);
            start = cursor;
        }
    }
    if start < range.end {
        push_span(spans, SpanKind::Unclassified, start, range.end);
    }
}

fn push_span(spans: &mut Vec<Span>, kind: SpanKind, start: usize, end: usize) {
    spans.push(Span {
        kind,
        range: start..end,
        decoded: 0,
        chain_start: 0,
    });
}

fn write_span(output: &mut impl Write, kind: &str, start: usize, end: usize) -> io::Result<()> {
    writeln!(
        output,
        "{kind}\t0x{start:x}\t0x{end:x}\t{}\t\t",
        end - start
    )
}
