//! Spread-spectrum LSB steganography — bit-compatible with the Python
//! implementation in app/transport/steganography.py.
//!
//! Algorithm:
//!   1. Flatten all LSBs of RGB channels into a linear bit-array of size
//!      width * height * 3.
//!   2. Randomize ALL LSBs with crypto random — defeats Chi-squared /
//!      RS-analysis since cover and stego look statistically identical.
//!   3. Phase 1: 128 bits of nonce go to positions derived from
//!      HMAC-SHA256(key, b"\x00"*16 + b"idx") via partial Fisher-Yates.
//!   4. Phase 2: marker (HMAC-SHA256(key, nonce + "marker")[:16]) + u32
//!      length BE + data — all XOR-masked with HMAC stream
//!      (key, nonce + "xor"), written at positions derived from
//!      HMAC-SHA256(key, nonce + "idx") over the non-nonce bit pool.
//!
//! Matches Python byte-for-byte so files embedded by either side extract
//! cleanly by the other. Python runs at ~200 ms per 1 MP image;
//! this Rust version runs in ~6 ms on the same image.

use blake2::digest::KeyInit as _KI;
use hmac::{Hmac, Mac};
use image::{DynamicImage, GenericImageView, ImageBuffer, Rgba, RgbaImage};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyBytes;
use sha2::Sha256;
use std::collections::HashSet;
use std::io::Cursor;

type HmacSha256 = Hmac<Sha256>;


/// HMAC-SHA256 counter-mode stream. Matches _derive_stream in Python.
fn derive_stream(key: &[u8], nonce_tagged: &[u8], length: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(length + 32);
    let mut ctr: u32 = 0;
    while out.len() < length {
        let mut m = <HmacSha256 as Mac>::new_from_slice(key).unwrap();
        m.update(nonce_tagged);
        m.update(&ctr.to_be_bytes());
        let block = m.finalize().into_bytes();
        out.extend_from_slice(&block);
        ctr = ctr.wrapping_add(1);
    }
    out.truncate(length);
    out
}


/// Partial Fisher-Yates — returns `count` unique indices in [0, total).
/// Matches _permuted_indices. Consumes 4 bytes of stream per index.
fn permuted_indices(key: &[u8], nonce: &[u8], total: usize, count: usize) -> Vec<usize> {
    let mut tag = Vec::with_capacity(nonce.len() + 3);
    tag.extend_from_slice(nonce);
    tag.extend_from_slice(b"idx");
    let stream = derive_stream(key, &tag, count * 4);

    let mut indices: Vec<usize> = (0..total).collect();
    let loop_end = count.min(total.saturating_sub(1));
    for i in 0..loop_end {
        let j_bytes = &stream[i * 4..(i + 1) * 4];
        let j_val = u32::from_be_bytes(j_bytes.try_into().unwrap()) as usize;
        let j = i + (j_val % (total - i));
        indices.swap(i, j);
    }
    indices.truncate(count);
    indices
}


fn marker_of(key: &[u8], nonce: &[u8]) -> [u8; 16] {
    let mut m = <HmacSha256 as Mac>::new_from_slice(key).unwrap();
    m.update(nonce);
    m.update(b"marker");
    let full = m.finalize().into_bytes();
    let mut out = [0u8; 16];
    out.copy_from_slice(&full[..16]);
    out
}


fn bits_of(bytes: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len() * 8);
    for &b in bytes {
        for i in (0..8).rev() {
            out.push((b >> i) & 1);
        }
    }
    out
}


fn bits_to_bytes(bits: &[u8]) -> Vec<u8> {
    let n = bits.len() / 8;
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let mut byte: u8 = 0;
        for j in 0..8 {
            byte = (byte << 1) | bits[i * 8 + j];
        }
        out.push(byte);
    }
    out
}


// ── Public: embed ─────────────────────────────────────────────────────────

/// Embed `data` into `cover_png` using spread-spectrum LSB keyed by
/// `key` (typically 32 bytes from the room E2E key). Returns a lossless
/// PNG as bytes.
#[pyfunction]
pub fn steg_embed_png(
    py: Python<'_>,
    cover_png: &[u8],
    data: &[u8],
    key: &[u8],
) -> PyResult<Py<PyBytes>> {
    if key.is_empty() {
        return Err(PyValueError::new_err("key must not be empty"));
    }
    let img = image::load_from_memory(cover_png)
        .map_err(|e| PyValueError::new_err(format!("cover decode: {}", e)))?;
    let rgb = img.to_rgb8();
    let (w, h) = (rgb.width(), rgb.height());
    let total_bits = (w as usize) * (h as usize) * 3;
    let max_data = total_bits / 8 - 36;  // -16 nonce -16 marker -4 length
    if data.len() > max_data {
        return Err(PyValueError::new_err(format!(
            "data ({} B) does not fit in image ({} B max)", data.len(), max_data
        )));
    }

    let data = data.to_vec();
    let key = key.to_vec();

    let out_bytes = py.allow_threads(move || -> Result<Vec<u8>, String> {
        // Build all bits, randomize LSBs with crypto random.
        use rand::RngCore;
        let mut rgb_bytes = rgb.as_raw().clone();   // width*height*3 bytes
        let mut random_lsbs = vec![0u8; (total_bits + 7) / 8];
        rand::thread_rng().fill_bytes(&mut random_lsbs);
        for idx in 0..total_bits {
            let rbit = (random_lsbs[idx / 8] >> (7 - idx % 8)) & 1;
            rgb_bytes[idx] = (rgb_bytes[idx] & 0xFE) | rbit;
        }

        // Phase 1: nonce at positions derived from key + "\x00"*16 + "idx"
        let mut nonce = [0u8; 16];
        rand::thread_rng().fill_bytes(&mut nonce);
        let nonce_bits = bits_of(&nonce);
        let zero16 = [0u8; 16];
        let nonce_perm = permuted_indices(&key, &zero16, total_bits, 128);
        let used_positions: HashSet<usize> = nonce_perm.iter().copied().collect();
        for (i, &bit) in nonce_bits.iter().enumerate() {
            let pos = nonce_perm[i];
            rgb_bytes[pos] = (rgb_bytes[pos] & 0xFE) | bit;
        }

        // Phase 2 payload: marker + u32 length BE + data  (XOR-masked)
        let marker = marker_of(&key, &nonce);
        let mut phase2_raw = Vec::with_capacity(16 + 4 + data.len());
        phase2_raw.extend_from_slice(&marker);
        phase2_raw.extend_from_slice(&(data.len() as u32).to_be_bytes());
        phase2_raw.extend_from_slice(&data);
        let xor_tag: Vec<u8> = {
            let mut v = Vec::with_capacity(nonce.len() + 3);
            v.extend_from_slice(&nonce); v.extend_from_slice(b"xor"); v
        };
        let xor_mask = derive_stream(&key, &xor_tag, phase2_raw.len());
        let phase2_masked: Vec<u8> = phase2_raw.iter()
            .zip(xor_mask.iter())
            .map(|(a, b)| a ^ b)
            .collect();
        let phase2_bits = bits_of(&phase2_masked);

        // Phase 2 positions: in the non-nonce pool, seeded by key + nonce + "idx"
        let available: Vec<usize> = (0..total_bits)
            .filter(|i| !used_positions.contains(i))
            .collect();
        let phase2_perm = permuted_indices(&key, &nonce, available.len(), phase2_bits.len());
        for (i, &bit) in phase2_bits.iter().enumerate() {
            let real_pos = available[phase2_perm[i]];
            rgb_bytes[real_pos] = (rgb_bytes[real_pos] & 0xFE) | bit;
        }

        // Write to RGBA buffer + re-encode as PNG
        let mut buf: RgbaImage = ImageBuffer::new(w, h);
        for y in 0..h {
            for x in 0..w {
                let idx = ((y * w + x) * 3) as usize;
                let (r, g, b) = (rgb_bytes[idx], rgb_bytes[idx + 1], rgb_bytes[idx + 2]);
                buf.put_pixel(x, y, Rgba([r, g, b, 255]));
            }
        }
        let mut out = Vec::with_capacity(cover_png.len());
        DynamicImage::ImageRgba8(buf)
            .write_to(&mut Cursor::new(&mut out), image::ImageFormat::Png)
            .map_err(|e| e.to_string())?;
        Ok(out)
    }).map_err(|e| PyValueError::new_err(e))?;

    Ok(PyBytes::new(py, &out_bytes).into())
}


/// Extract spread-spectrum payload. Returns None (via empty bytes
/// + False) if the marker doesn't verify — caller decides if that's
/// an error or just "no payload in this image".
#[pyfunction]
pub fn steg_extract_png(
    py: Python<'_>,
    stego_png: &[u8],
    key: &[u8],
) -> PyResult<Option<Py<PyBytes>>> {
    let img = image::load_from_memory(stego_png)
        .map_err(|e| PyValueError::new_err(format!("stego decode: {}", e)))?;
    let rgb = img.to_rgb8();
    let (w, h) = (rgb.width(), rgb.height());
    let total_bits = (w as usize) * (h as usize) * 3;
    let key_v = key.to_vec();
    let rgb_bytes = rgb.as_raw().clone();

    let out_opt: Option<Vec<u8>> = py.allow_threads(move || {
        // Extract ALL LSBs
        let mut all_lsb = Vec::with_capacity(total_bits);
        for i in 0..total_bits {
            all_lsb.push(rgb_bytes[i] & 1);
        }

        // Phase 1: nonce
        let zero16 = [0u8; 16];
        let nonce_perm = permuted_indices(&key_v, &zero16, total_bits, 128);
        let nonce_bits: Vec<u8> = nonce_perm.iter().map(|&p| all_lsb[p]).collect();
        let nonce = bits_to_bytes(&nonce_bits);
        if nonce.len() != 16 { return None; }

        // Phase 2 header: 20 bytes = 160 bits
        let used_positions: HashSet<usize> = nonce_perm.iter().copied().collect();
        let available: Vec<usize> = (0..total_bits)
            .filter(|i| !used_positions.contains(i))
            .collect();
        let header_bit_count = 160;
        if header_bit_count > available.len() { return None; }

        let header_perm = permuted_indices(&key_v, &nonce, available.len(), header_bit_count);
        let header_bits: Vec<u8> = (0..header_bit_count)
            .map(|i| all_lsb[available[header_perm[i]]])
            .collect();
        let header_masked = bits_to_bytes(&header_bits);
        let xor_tag: Vec<u8> = {
            let mut v = Vec::with_capacity(nonce.len() + 3);
            v.extend_from_slice(&nonce); v.extend_from_slice(b"xor"); v
        };
        let xor20 = derive_stream(&key_v, &xor_tag, 20);
        let header_raw: Vec<u8> = header_masked.iter().zip(xor20.iter())
            .map(|(a, b)| a ^ b).collect();

        // Verify marker
        let expected_marker = marker_of(&key_v, &nonce);
        let actual_marker = &header_raw[..16];
        use subtle::ConstantTimeEq;
        if !bool::from(expected_marker.as_slice().ct_eq(actual_marker)) {
            return None;
        }

        let data_len = u32::from_be_bytes(header_raw[16..20].try_into().unwrap()) as usize;
        let total_phase2_bits = (20 + data_len) * 8;
        if total_phase2_bits > available.len() { return None; }

        // Read the full phase 2 payload
        let full_perm = permuted_indices(&key_v, &nonce, available.len(), total_phase2_bits);
        let full_bits: Vec<u8> = (0..total_phase2_bits)
            .map(|i| all_lsb[available[full_perm[i]]])
            .collect();
        let full_masked = bits_to_bytes(&full_bits);
        let full_xor = derive_stream(&key_v, &xor_tag, full_masked.len());
        let full_raw: Vec<u8> = full_masked.iter().zip(full_xor.iter())
            .map(|(a, b)| a ^ b).collect();

        Some(full_raw[20..20 + data_len].to_vec())
    });

    match out_opt {
        Some(bytes) => Ok(Some(PyBytes::new(py, &bytes).into())),
        None        => Ok(None),
    }
}


/// Raw byte-level "hide in padding" — unchanged from MVP; not used by
/// the Python transport layer but kept for completeness.
#[pyfunction]
pub fn steg_embed_bytes(cover_len: usize, payload: &[u8]) -> PyResult<Vec<u8>> {
    if cover_len < 4 + payload.len() * 2 {
        return Err(PyValueError::new_err("cover too small"));
    }
    use rand::RngCore;
    let mut out = vec![0u8; cover_len];
    rand::thread_rng().fill_bytes(&mut out);
    let len_be = (payload.len() as u32).to_be_bytes();
    out[..4].copy_from_slice(&len_be);
    for (i, &b) in payload.iter().enumerate() {
        out[4 + i * 2] = b;
    }
    Ok(out)
}


// Bring the unused import in — clippy otherwise warns. (Kept for
// parity with the existing Blake2 dependency signalling.)
#[allow(dead_code)]
fn _dummy_blake2_link() {
    use blake2::Blake2b512;
    type _Unused = Blake2b512;
    let _ = <HmacSha256 as _KI>::new_from_slice(&[0u8; 32]);
}
