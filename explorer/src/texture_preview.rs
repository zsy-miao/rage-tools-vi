//! Conservative preview for the verified 64×64 single-mip BC3 control layout.
use crate::image_preview::ImagePreview;
use annoyed_tools::{archive::Archive, index};
use std::io::{self, Write};
use std::path::Path;

struct Limited { bytes: Vec<u8>, limit: usize }
impl Write for Limited {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self.bytes.len().saturating_add(data.len()) > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData, "Texture candidate exceeds preview limit")); }
        self.bytes.extend_from_slice(data);
        Ok(data.len())
    }
    fn flush(&mut self) -> io::Result<()> { Ok(()) }
}

fn u16le(data: &[u8], offset: usize) -> Option<u16> { Some(u16::from_le_bytes(data.get(offset..offset.checked_add(2)?)?.try_into().ok()?)) }
fn u32le(data: &[u8], offset: usize) -> Option<u32> { Some(u32::from_le_bytes(data.get(offset..offset.checked_add(4)?)?.try_into().ok()?)) }
fn u64le(data: &[u8], offset: usize) -> Option<u64> { Some(u64::from_le_bytes(data.get(offset..offset.checked_add(8)?)?.try_into().ok()?)) }
fn sys_offset(pointer: u64, size: usize, length: usize) -> Option<usize> {
    let offset = usize::try_from(pointer.checked_sub(0x50000000)?).ok()?;
    (offset.checked_add(length)? <= size).then_some(offset)
}
fn joaat(bytes: &[u8]) -> u32 {
    let mut value = 0u32;
    for byte in bytes { value = value.wrapping_add(byte.to_ascii_lowercase() as u32); value = value.wrapping_add(value << 10); value ^= value >> 6; }
    value = value.wrapping_add(value << 3); value ^= value >> 11; value.wrapping_add(value << 15)
}

fn descriptor(system: &[u8]) -> Option<String> {
    let hash_ptr = u64le(system, 0x20)?;
    let ptr_ptr = u64le(system, 0x30)?;
    if (u16le(system, 0x28)?, u16le(system, 0x2a)?, u16le(system, 0x38)?, u16le(system, 0x3a)?) != (1, 1, 1, 1) { return None; }
    let hash_pos = sys_offset(hash_ptr, system.len(), 4)?;
    let ptr_pos = sys_offset(ptr_ptr, system.len(), 8)?;
    let descriptor = sys_offset(u64le(system, ptr_pos)?, system.len(), 0x40)?;
    if u32le(system, descriptor + 8)? != 256 || u16le(system, descriptor + 12)? != 16 || u16le(system, descriptor + 14)? != 8 || u64le(system, descriptor + 16)? != 0x980 || u64le(system, descriptor + 24)? != 0x60000000 { return None; }
    if (u16le(system, descriptor + 0x38)?, u16le(system, descriptor + 0x3a)?, u16le(system, descriptor + 0x3c)?, *system.get(descriptor + 0x3e)?, *system.get(descriptor + 0x3f)?) != (64, 64, 1, 1, 0x4d) { return None; }
    let name_pos = sys_offset(u64le(system, descriptor + 0x30)?, system.len(), 9)?.checked_add(8)?;
    let tail = system.get(name_pos..)?;
    let length = tail.iter().position(|&b| b == 0)?;
    if length == 0 || length > 128 { return None; }
    let name = &tail[..length];
    if !name.iter().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'_') || joaat(name) != u32le(system, hash_pos)? { return None; }
    String::from_utf8(name.to_vec()).ok()
}

fn deposit(mut value: u32, mut mask: u32) -> u32 {
    let mut result = 0;
    while mask != 0 && value != 0 { let bit = mask & mask.wrapping_neg(); if value & 1 != 0 { result |= bit; } mask ^= bit; value >>= 1; }
    result
}
fn rgb565(value: u16) -> [u8; 3] { [(((value >> 11) & 31) * 255 / 31) as u8, (((value >> 5) & 63) * 255 / 63) as u8, ((value & 31) * 255 / 31) as u8] }

fn decode_bc3(data: &[u8]) -> Option<Vec<u8>> {
    if data.len() != 4096 { return None; }
    let mut rgba = vec![0; 64 * 64 * 4];
    for y in 0..16u32 { for x in 0..16u32 {
        let offset = (deposit(16 * x, 0xaacf) | deposit(y, 0x5530)) as usize;
        let block = data.get(offset..offset + 16)?;
        let a0 = block[0] as u32; let a1 = block[1] as u32;
        let mut alpha = [0u8; 8]; alpha[0] = a0 as u8; alpha[1] = a1 as u8;
        if a0 > a1 { for i in 1..=6 { alpha[i + 1] = (((7 - i) as u32 * a0 + i as u32 * a1) / 7) as u8; } }
        else { for i in 1..=4 { alpha[i + 1] = (((5 - i) as u32 * a0 + i as u32 * a1) / 5) as u8; } alpha[6] = 0; alpha[7] = 255; }
        let mut alpha_bits = 0u64; for (i, byte) in block[2..8].iter().enumerate() { alpha_bits |= (*byte as u64) << (8 * i); }
        let c0 = rgb565(u16::from_le_bytes([block[8], block[9]]));
        let c1 = rgb565(u16::from_le_bytes([block[10], block[11]]));
        let color_bits = u32::from_le_bytes(block[12..16].try_into().ok()?);
        for i in 0..16u32 {
            let choice = ((color_bits >> (2 * i)) & 3) as usize;
            let a = alpha[((alpha_bits >> (3 * i)) & 7) as usize];
            let dest = (((y * 4 + i / 4) * 64 + x * 4 + i % 4) * 4) as usize;
            for channel in 0..3 {
                rgba[dest + channel] = match choice { 0 => c0[channel], 1 => c1[channel], 2 => ((2 * c0[channel] as u16 + c1[channel] as u16) / 3) as u8, _ => ((c0[channel] as u16 + 2 * c1[channel] as u16) / 3) as u8 };
            }
            rgba[dest + 3] = a;
        }
    } }
    Some(rgba)
}

pub fn load(archive: &Archive, index_path: &Path, range: &index::Range) -> io::Result<Option<ImagePreview>> {
    let (prefix, _) = archive.decoded_prefix(range.start, range.end, false, 80)?;
    if prefix.len() < 0x40 || u16le(&prefix, 0x28) != Some(1) || u16le(&prefix, 0x38) != Some(1) { return Ok(None); }
    let mut reader = archive.reader()?;
    let mut system = Limited { bytes: Vec::new(), limit: 1024 * 1024 };
    if reader.decode_zlib_into(range.start, range.end, &mut system).is_err() { return Ok(None); }
    let Some(name) = descriptor(&system.bytes) else { return Ok(None); };
    let next_start = range.end.checked_add(15).map(|v| v & !15).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Range alignment overflow"))?;
    let position = index::seek_offset(index_path, range.end)?;
    let page = index::page(index_path, position, "")?;
    let Some(graphics) = page.rows.into_iter().find(|item| item.start == next_start && item.kind == "zlib") else { return Ok(None); };
    let mut buffer = Limited { bytes: Vec::new(), limit: 4096 };
    if reader.decode_zlib_into(graphics.start, graphics.end, &mut buffer).is_err() { return Ok(None); }
    let Some(rgba) = decode_bc3(&buffer.bytes) else { return Ok(None); };
    Ok(Some(ImagePreview { width: 64, height: 64, rgba, description: format!("Native BC3 candidate · {name} · 64 × 64 · single mip (control-validated layout)") }))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn trophy_matches_independent_control_png() {
        let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../textures.rpf");
        let expected = Path::new(env!("CARGO_MANIFEST_DIR")).join("../output/texture-control/trophy.png");
        if !source.exists() || !expected.exists() { return; }
        let archive = Archive::open(&source).unwrap();
        let index_path = std::env::temp_dir().join(format!("annoyed-texture-{}.tsv", std::process::id()));
        let a = 0x9160010u64; let b = 0x916006bu64; let c = 0x9160070u64; let d = 0x91603aeu64;
        let text = format!("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\nunclassified\t0x0\t0x{a:x}\t{a}\t\t\nzlib\t0x{a:x}\t0x{b:x}\t{}\t240\t0x{a:x}\nunclassified\t0x{b:x}\t0x{c:x}\t{}\t\t\nzlib\t0x{c:x}\t0x{d:x}\t{}\t4096\t0x{c:x}\nunclassified\t0x{d:x}\t0x{:x}\t{}\t\t\n", b-a, c-b, d-c, archive.size, archive.size-d);
        std::fs::write(&index_path, text).unwrap();
        let range = index::Range { kind: "zlib".into(), start: a, end: b, decoded: "240".into(), text_prefix: String::new() };
        let preview = load(&archive, &index_path, &range).unwrap().unwrap();
        let reference = image::open(expected).unwrap().to_rgba8();
        assert_eq!((preview.width, preview.height), (64, 64));
        assert_eq!(preview.rgba, reference.into_raw());
        assert!(preview.description.contains("trophy"));
        std::fs::remove_file(index_path).unwrap();
    }
}
