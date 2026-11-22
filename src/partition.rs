use super::range_map::{payload_range, scan_payload, Span, SpanKind};
use super::{word, PAGE_SIZE, RPF9_MAGIC, STREAM_ALIGNMENT};
use std::collections::BTreeMap;
use std::error::Error;
use std::io::Write;
use std::ops::Range;

const MIN_NESTED_GAP: usize = 0x100;

#[derive(Default)]
struct PayloadSummary {
    chains: BTreeMap<usize, Chain>,
    opaque: Vec<Range<usize>>,
    zero_bytes: usize,
    streams: usize,
    zlib_bytes: usize,
}

#[derive(Default)]
struct Chain {
    end: usize,
    decoded: usize,
}

impl PayloadSummary {
    fn include(&mut self, spans: Vec<Span>) {
        for span in spans {
            match span.kind {
                SpanKind::Zlib => {
                    let chain = self.chains.entry(span.chain_start).or_default();
                    chain.end = span.range.end;
                    chain.decoded += span.decoded;
                    self.streams += 1;
                    self.zlib_bytes += span.range.len();
                }
                SpanKind::Unclassified => self.opaque.push(span.range),
                SpanKind::ZeroRun => self.zero_bytes += span.range.len(),
            }
        }
    }

    fn candidates(&self) -> usize {
        self.chains.len() + self.opaque.len()
    }
}

/// Describe one candidate partition. The header count is a consistency check.
pub(super) fn write_partition(
    output: &mut impl Write,
    data: &[u8],
    pack_range: Range<usize>,
) -> Result<(), Box<dyn Error>> {
    let payload = payload_range(data, pack_range.clone())?;
    let count_like = word(&data[pack_range], 0x24) as usize;
    let (embedded, unresolved) = resolve_embedded(data, payload.clone());

    let mut summary = PayloadSummary::default();
    let mut cursor = payload.start;
    for child in &embedded {
        summary.include(scan_payload(data, cursor..child.start));
        cursor = child.end;
    }
    summary.include(scan_payload(data, cursor..payload.end));

    let opaque_bytes = summary.opaque.iter().map(Range::len).sum::<usize>();
    let embedded_bytes = embedded.iter().map(Range::len).sum::<usize>();
    let candidates = summary.candidates() + embedded.len();
    let comparison = match candidates.cmp(&count_like) {
        std::cmp::Ordering::Equal => "match",
        std::cmp::Ordering::Greater => "over",
        std::cmp::Ordering::Less => "under",
    };

    writeln!(output, "metric\tvalue")?;
    writeln!(output, "word_24\t{count_like}")?;
    writeln!(output, "verified_streams\t{}", summary.streams)?;
    writeln!(output, "candidate_zlib_chains\t{}", summary.chains.len())?;
    writeln!(output, "opaque_spans\t{}", summary.opaque.len())?;
    writeln!(output, "inferred_embedded_packs\t{}", embedded.len())?;
    writeln!(output, "unresolved_embedded_headers\t{}", unresolved.len())?;
    writeln!(output, "candidate_entries\t{candidates}")?;
    writeln!(output, "payload_bytes\t{}", payload.len())?;
    writeln!(output, "zlib_bytes\t{}", summary.zlib_bytes)?;
    writeln!(output, "opaque_bytes\t{opaque_bytes}")?;
    writeln!(output, "inferred_embedded_bytes\t{embedded_bytes}")?;
    writeln!(output, "zero_run_bytes\t{}", summary.zero_bytes)?;
    writeln!(output, "count_comparison\t{comparison}")?;

    writeln!(output, "\ncandidate\tstart\tend\tspan_bytes\tdecoded_bytes")?;
    for extent in embedded {
        write_candidate(output, "embedded_rpf9", extent)?;
    }
    for offset in unresolved {
        writeln!(output, "unresolved_rpf9_header\t0x{offset:x}\t\t\t")?;
    }
    for span in summary.opaque {
        write_candidate(output, "opaque", span)?;
    }
    for (start, chain) in summary.chains {
        writeln!(
            output,
            "zlib_chain\t0x{start:x}\t0x{:x}\t{}\t{}",
            chain.end,
            chain.end - start,
            chain.decoded,
        )?;
    }
    Ok(())
}

fn write_candidate(output: &mut impl Write, kind: &str, extent: Range<usize>) -> std::io::Result<()> {
    writeln!(
        output,
        "{kind}\t0x{:x}\t0x{:x}\t{}\t",
        extent.start,
        extent.end,
        extent.len(),
    )
}

/// Keep a nested extent only when one tested endpoint survives the checks.
/// Ambiguous headers stay visible and their bytes remain in the parent scan.
fn resolve_embedded(data: &[u8], payload: Range<usize>) -> (Vec<Range<usize>>, Vec<usize>) {
    let headers: Vec<_> = (payload.start.next_multiple_of(PAGE_SIZE)..payload.end)
        .step_by(PAGE_SIZE)
        .filter(|&offset| {
            data[offset..payload.end].starts_with(RPF9_MAGIC)
                && payload_range(data, offset..payload.end).is_ok()
        })
        .collect();

    let mut resolved = Vec::new();
    let mut unresolved = Vec::new();
    for (index, &start) in headers.iter().enumerate() {
        let limit = headers.get(index + 1).copied().unwrap_or(payload.end);
        let trailer_bytes = word(&data[start..], 12) as usize;
        let count_like = word(&data[start..], 0x24) as usize;
        let mut viable = candidate_ends(data, start, limit).into_iter().filter(|&end| {
            let Ok(payload) = payload_range(data, start..end) else {
                return false;
            };
            if trailer_bytes == 0
                || end % STREAM_ALIGNMENT != 0
                || !data[end - trailer_bytes.min(STREAM_ALIGNMENT)..end]
                    .iter()
                    .any(|&byte| byte != 0)
            {
                return false;
            }
            let mut summary = PayloadSummary::default();
            summary.include(scan_payload(data, payload));
            summary.candidates() == count_like
        });
        match (viable.next(), viable.next()) {
            (Some(end), None) => resolved.push(start..end),
            _ => unresolved.push(start),
        }
    }
    (resolved, unresolved)
}

fn candidate_ends(data: &[u8], start: usize, limit: usize) -> Vec<usize> {
    let mut ends = Vec::new();
    let mut cursor = start;
    while cursor < limit {
        if data[cursor] != 0 {
            cursor += 1;
            continue;
        }
        let zero_start = cursor;
        while cursor < limit && data[cursor] == 0 {
            cursor += 1;
        }
        if cursor - zero_start >= MIN_NESTED_GAP && zero_start > start {
            ends.push(zero_start);
        }
    }
    ends.push(limit);
    ends
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_header(data: &mut [u8], count_like: u32, trailer_bytes: u32) {
        data[..4].copy_from_slice(RPF9_MAGIC);
        for (field, value) in [(4, 0x40u32), (12, trailer_bytes), (0x24, count_like)] {
            data[field..field + 4].copy_from_slice(&value.to_le_bytes());
        }
    }

    #[test]
    fn embedded_pack_excludes_surrounding_zero_padding() {
        let mut data = vec![0; 0x3000];
        write_header(&mut data, 1, 0x40);
        write_header(&mut data[0x1000..], 2, 0x10);
        data[0x1040..0x1800].fill(0xaa);
        data[0x1900..0x2000].fill(0xbb);
        data[0x2000..0x2010].fill(0xcc);

        let mut output = Vec::new();
        write_partition(&mut output, &data, 0..data.len()).unwrap();
        let report = String::from_utf8(output).unwrap();
        assert!(report.contains("embedded_rpf9\t0x1000\t0x2010\t"), "{report}");
        assert!(report.contains("opaque_spans\t0\n"), "{report}");
        assert!(report.contains("candidate_entries\t1\n"), "{report}");
    }

    #[test]
    fn ambiguous_embedded_endpoints_stay_unresolved() {
        let mut data = vec![0; 0x3000];
        write_header(&mut data, 1, 0x40);
        write_header(&mut data[0x1000..], 1, 0x10);
        data[0x1040..0x1800].fill(0xaa);
        // A second candidate trailer after a zero gap adds no payload span.
        data[0x1a00..0x1a10].fill(0xbb);

        let mut output = Vec::new();
        write_partition(&mut output, &data, 0..data.len()).unwrap();
        let report = String::from_utf8(output).unwrap();
        assert!(report.contains("inferred_embedded_packs\t0\n"), "{report}");
        assert!(report.contains("unresolved_rpf9_header\t0x1000\t"), "{report}");
    }

    #[test]
    fn reports_count_shortfall_without_discarding_small_spans() {
        let mut data = vec![0; 0x400];
        write_header(&mut data, 3, 0x40);
        data[0x40..0x48].fill(0xcc);
        let mut output = Vec::new();
        write_partition(&mut output, &data, 0..data.len()).unwrap();
        let report = String::from_utf8(output).unwrap();
        assert!(report.contains("opaque_bytes\t8\n"), "{report}");
        assert!(report.contains("candidate_entries\t1\n"), "{report}");
        assert!(report.contains("count_comparison\tunder\n"), "{report}");
    }
}
