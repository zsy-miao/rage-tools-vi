use super::{word, RPF9_MAGIC, STREAM_ALIGNMENT};
use std::error::Error;
use std::io::Write;
use std::ops::Range;

const SHARED_BYTES: Range<usize> = 0x40..0x60;

pub(super) fn write_packs(
    output: &mut impl Write,
    data: &[u8],
    range: Range<usize>,
) -> Result<(), Box<dyn Error>> {
    let pack = data.get(range.clone()).ok_or("invalid pack byte range")?;
    if !pack.starts_with(RPF9_MAGIC) {
        return Err("pack range must begin with an RPF9 header".into());
    }
    let reference = data
        .get(SHARED_BYTES)
        .ok_or("archive is shorter than the observed header")?;

    writeln!(
        output,
        "header_offset\tfront_end\tfront_block_start\ttrailer_bytes\tword_24\tfront_entropy\tfront_block_entropy\tshared_0x40\ttrailer_start\ttrailer_entropy"
    )?;
    for relative in (0..pack.len()).step_by(STREAM_ALIGNMENT) {
        let head = &pack[relative..];
        if !head.starts_with(RPF9_MAGIC) {
            continue;
        }
        let absolute = range.start + relative;
        if head.len() < SHARED_BYTES.end {
            if relative == 0 {
                return Err("pack range is shorter than the observed header".into());
            }
            continue;
        }
        let front_end = word(head, 4) as usize;
        let front_block_start = word(head, 8) as usize;
        let trailer_bytes = word(head, 12) as usize;
        let trailer_start = head.len().checked_sub(trailer_bytes);
        if !(SHARED_BYTES.end..=front_end).contains(&front_block_start)
            || trailer_start.is_none_or(|start| front_end > start)
        {
            if relative == 0 {
                return Err("front metadata or trailer exceeds the supplied pack bounds".into());
            }
            continue;
        }

        write!(
            output,
            "0x{absolute:x}\t0x{:x}\t0x{:x}\t{trailer_bytes}\t{}\t{:.4}\t{:.4}\t{}\t",
            absolute + front_end,
            absolute + front_block_start,
            word(head, 0x24),
            shannon(&head[SHARED_BYTES.end..front_end]),
            shannon(&head[front_block_start..front_end]),
            &head[SHARED_BYTES] == reference,
        )?;
        // Only the selected pack has a known end. A nested header gives a size
        // without a reliable location for its trailer.
        if let Some(start) = trailer_start.filter(|_| relative == 0 && trailer_bytes != 0) {
            writeln!(output, "0x{:x}\t{:.4}", absolute + start, shannon(&head[start..]))?;
        } else {
            writeln!(output, "\t")?;
        }
    }
    Ok(())
}

fn shannon(bytes: &[u8]) -> f64 {
    let mut counts = [0usize; 256];
    for &byte in bytes {
        counts[byte as usize] += 1;
    }
    counts
        .into_iter()
        .filter(|&count| count != 0)
        .map(|count| {
            let probability = count as f64 / bytes.len() as f64;
            -probability * probability.log2()
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn measures_trailers_at_pack_ends() {
        let mut data = vec![0; 0x220];
        for start in [0, 0x100] {
            data[start..start + 4].copy_from_slice(RPF9_MAGIC);
            for (field, value) in [(4, 0x80u32), (8, 0x70), (12, 0x10)] {
                data[start + field..start + field + 4].copy_from_slice(&value.to_le_bytes());
            }
        }
        let distinct_bytes: Vec<u8> = (0..16).collect();
        data[0x210..0x220].copy_from_slice(&distinct_bytes);
        data[0x1b0..0x1c0].copy_from_slice(&distinct_bytes);

        let mut output = Vec::new();
        write_packs(&mut output, &data, 0..data.len()).unwrap();
        let report = String::from_utf8(output).unwrap();
        let mut rows = report.lines().skip(1);
        assert!(rows.next().unwrap().ends_with("\t0x210\t4.0000"));
        assert!(rows.next().unwrap().ends_with("\ttrue\t\t"));
        assert!(rows.next().is_none());

        let mut output = Vec::new();
        write_packs(&mut output, &data, 0x100..0x1c0).unwrap();
        let report = String::from_utf8(output).unwrap();
        assert!(report.lines().nth(1).unwrap().ends_with("\t0x1b0\t4.0000"));
    }
}
