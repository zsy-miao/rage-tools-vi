use super::{decode_zlib, STREAM_ALIGNMENT, ZLIB_CHUNK_SIZE};

pub(super) fn decode_chain(input: &[u8], start: usize) -> Result<(Vec<u8>, usize), String> {
    if start % STREAM_ALIGNMENT != 0 {
        return Err("zlib start must be 16-byte aligned".into());
    }

    let mut decoded = Vec::new();
    let mut cursor = 0;
    let mut streams = 0;
    loop {
        let (stored_size, chunk) = decode_zlib(&input[cursor..], &[])
            .ok_or_else(|| format!("no checksum-valid zlib stream at 0x{:x}", start + cursor))?;
        let end = cursor + stored_size;
        let decoded_size = chunk.len();
        streams += 1;
        decoded.extend(chunk);
        if end == input.len() {
            return Ok((decoded, streams));
        }
        if decoded_size != ZLIB_CHUNK_SIZE {
            return Err(format!(
                "short zlib chunk ends before range end at 0x{:x}",
                start + end
            ));
        }
        let next = end.next_multiple_of(STREAM_ALIGNMENT);
        if next >= input.len() || input[end..next].iter().any(|&byte| byte != 0) {
            return Err(format!(
                "invalid zlib continuation padding at 0x{:x}",
                start + end
            ));
        }
        cursor = next;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{write::ZlibEncoder, Compression};
    use std::io::Write;

    fn compress(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    #[test]
    fn extracts_aligned_continuations_and_checks_the_final_checksum() {
        let mut expected = vec![1; ZLIB_CHUNK_SIZE];
        let mut stored = compress(&expected);
        stored.resize(stored.len().next_multiple_of(STREAM_ALIGNMENT), 0);
        let last_chunk = b"tail";
        stored.extend(compress(last_chunk));
        expected.extend(last_chunk);

        let (decoded, streams) = decode_chain(&stored, 0x1000).unwrap();
        assert_eq!(decoded, expected);
        assert_eq!(streams, 2);

        *stored.last_mut().unwrap() ^= 1;
        assert!(decode_chain(&stored, 0x1000).is_err());
    }
}
