use annoyed_tools::archive::Archive;
use std::io::{self, Cursor};

#[derive(Debug, Clone)]
pub struct ImagePreview { pub width: u32, pub height: u32, pub rgba: Vec<u8>, pub description: String }

pub fn load(archive: &Archive, start: u64, end: u64, raw: bool) -> io::Result<Option<ImagePreview>> {
    let (prefix, _) = archive.decoded_prefix(start, end, raw, 16)?;
    let format = if prefix.starts_with(b"\x89PNG\r\n\x1a\n") { image::ImageFormat::Png }
        else if prefix.starts_with(b"\xff\xd8\xff") { image::ImageFormat::Jpeg }
        else { return Ok(None); };
    let (data, truncated) = archive.decoded_prefix(start, end, raw, 8 * 1024 * 1024)?;
    if truncated { return Err(io::Error::new(io::ErrorKind::InvalidData, "Image exceeds the 8 MiB preview limit")); }
    let mut reader = image::ImageReader::with_format(Cursor::new(data), format);
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(2048);
    limits.max_image_height = Some(2048);
    limits.max_alloc = Some(64 * 1024 * 1024);
    reader.limits(limits);
    let decoded = reader.decode().map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?.into_rgba8();
    let (width, height) = decoded.dimensions();
    let format_name = if format == image::ImageFormat::Png { "PNG" } else { "JPEG" };
    Ok(Some(ImagePreview { width, height, rgba: decoded.into_raw(), description: format!("{format_name} image · {width} × {height}{}", if raw { " · raw DEFLATE has no checksum" } else { "" }) }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::path::PathBuf;
    #[test]
    fn decodes_small_png_from_a_zlib_stream() {
        let mut png = Cursor::new(Vec::new());
        image::DynamicImage::ImageRgba8(image::RgbaImage::from_pixel(16, 16, image::Rgba([20, 160, 90, 255])))
            .write_to(&mut png, image::ImageFormat::Png).unwrap();
        let path: PathBuf = std::env::temp_dir().join(format!("annoyed-image-{}.rpf", std::process::id()));
        let mut file = std::fs::File::create(&path).unwrap();
        let mut header = [0u8; 96]; header[..4].copy_from_slice(b"9FPR");
        file.write_all(&header).unwrap();
        let mut encoder = flate2::write::ZlibEncoder::new(file, flate2::Compression::default());
        encoder.write_all(png.get_ref()).unwrap();
        encoder.finish().unwrap();
        let archive = Archive::open(&path).unwrap();
        let preview = load(&archive, 96, archive.size, false).unwrap().unwrap();
        assert_eq!((preview.width, preview.height), (16, 16));
        assert_eq!(&preview.rgba[..4], &[20, 160, 90, 255]);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn rejects_oversized_dimensions() {
        let mut png = Cursor::new(Vec::new());
        image::DynamicImage::ImageRgba8(image::RgbaImage::from_pixel(2049, 1, image::Rgba([0, 0, 0, 255])))
            .write_to(&mut png, image::ImageFormat::Png).unwrap();
        let path = std::env::temp_dir().join(format!("annoyed-large-image-{}.rpf", std::process::id()));
        let mut file = std::fs::File::create(&path).unwrap();
        let mut header = [0u8; 96]; header[..4].copy_from_slice(b"9FPR");
        file.write_all(&header).unwrap();
        let mut encoder = flate2::write::ZlibEncoder::new(file, flate2::Compression::default());
        encoder.write_all(png.get_ref()).unwrap();
        encoder.finish().unwrap();
        let archive = Archive::open(&path).unwrap();
        assert!(load(&archive, 96, archive.size, false).is_err());
        std::fs::remove_file(path).unwrap();
    }
}
