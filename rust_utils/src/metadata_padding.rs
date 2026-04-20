//! Metadata padding — pads messages to fixed-size buckets so the server
//! can't distinguish a 5-byte ACK from a 500-byte image reference by
//! ciphertext length alone.
//!
//! Matches app/chats/messages/padding.py:
//!   bucket = first bucket in BUCKET_SIZES that is >= plaintext_len + 2
//!   pad_len = bucket - plaintext_len - 2
//!   padded = [plaintext_len_be_u16 (2 bytes)] || plaintext || random_padding
//!   unpad returns plaintext[:prefix_u16]

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyBytes;
use rand::RngCore;

// Default bucket sizes — operator can override via the Python
// constant. Values chosen as log-spaced typical message sizes.
const BUCKETS: &[usize] = &[
    64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536,
];

#[pyfunction]
pub fn pad_to_bucket(py: Python<'_>, plaintext: &[u8]) -> PyResult<Py<PyBytes>> {
    if plaintext.len() > 65534 {
        return Err(PyValueError::new_err("plaintext exceeds 64 KiB padding limit"));
    }
    let pt = plaintext.to_vec();
    let out = py.allow_threads(move || {
        let needed = pt.len() + 2;
        let bucket = BUCKETS.iter().copied().find(|&b| b >= needed).unwrap_or(65536);
        let mut out = Vec::with_capacity(bucket);
        // 2-byte big-endian length prefix
        out.push((pt.len() >> 8) as u8);
        out.push((pt.len() & 0xFF) as u8);
        out.extend_from_slice(&pt);
        // Random fill up to bucket
        let mut rand_buf = vec![0u8; bucket - out.len()];
        rand::thread_rng().fill_bytes(&mut rand_buf);
        out.extend_from_slice(&rand_buf);
        out
    });
    Ok(PyBytes::new(py, &out).into())
}

#[pyfunction]
pub fn unpad_from_bucket(py: Python<'_>, padded: &[u8]) -> PyResult<Py<PyBytes>> {
    if padded.len() < 2 {
        return Err(PyValueError::new_err("padded payload too short"));
    }
    let len = ((padded[0] as usize) << 8) | (padded[1] as usize);
    if 2 + len > padded.len() {
        return Err(PyValueError::new_err(format!(
            "declared length {} exceeds padded buffer {}", len, padded.len() - 2
        )));
    }
    let plaintext = padded[2..2 + len].to_vec();
    Ok(PyBytes::new(py, &plaintext).into())
}

/// Return the bucket size that a given plaintext would pad up to —
/// useful for UI / analytics.
#[pyfunction]
pub fn pad_bucket_for(plaintext_len: usize) -> PyResult<usize> {
    let needed = plaintext_len + 2;
    Ok(BUCKETS.iter().copied().find(|&b| b >= needed).unwrap_or(65536))
}
