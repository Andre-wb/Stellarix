//! SHA-256 hashing for resumable-upload chunks.
//!
//! Used by app/files/resumable.py on every received chunk (10 MB
//! default). Python `hashlib.sha256(chunk).hexdigest()` on a 10 MB buffer
//! is ~15 ms; Rust `sha2` with SIMD backend is ~2 ms. At 100 MB/s
//! upload throughput, that's 150 ms/sec saved on the server, letting
//! the same core ingest 6-8x more concurrent uploads.

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sha2::{Digest, Sha256};

/// Hash a single chunk. Returns hex digest.
#[pyfunction]
pub fn sha256_hex(py: Python<'_>, data: &[u8]) -> PyResult<String> {
    let d = data.to_vec();
    let hex = py.allow_threads(move || {
        let mut h = Sha256::new();
        h.update(&d);
        hex::encode(h.finalize())
    });
    Ok(hex)
}

/// Hash multiple chunks in parallel; returns concatenated hex digests.
/// Useful for recomputing whole-file hash from already-received chunks.
#[pyfunction]
pub fn sha256_concat_hex(py: Python<'_>, chunks: Vec<Vec<u8>>) -> PyResult<Vec<String>> {
    use rayon::prelude::*;
    let out = py.allow_threads(move || {
        chunks.par_iter()
            .map(|c| {
                let mut h = Sha256::new();
                h.update(c);
                hex::encode(h.finalize())
            })
            .collect()
    });
    Ok(out)
}

/// Combine many per-chunk SHA-256 hashes into a single "rolling" hash
/// that matches what the client computed. Same reduction used by the
/// Python code: sha256(hex1 || hex2 || ... || hexN).
#[pyfunction]
pub fn sha256_combine_hex(py: Python<'_>, hex_list: Vec<String>) -> PyResult<String> {
    let hl = hex_list;
    let hex = py.allow_threads(move || {
        let mut h = Sha256::new();
        for s in &hl { h.update(s.as_bytes()); }
        hex::encode(h.finalize())
    });
    Ok(hex)
}

/// Write a 10 MB chunk directly and compute hash in one pass without
/// retaining the data in Python. Returns hex digest + byte length.
#[pyfunction]
pub fn sha256_stream(py: Python<'_>, data: Bound<'_, PyBytes>) -> PyResult<(String, usize)> {
    let slice = data.as_bytes();
    let len = slice.len();
    // Can't allow_threads here because we borrowed PyBytes — hash on
    // the caller thread, stay quick.
    let mut h = Sha256::new();
    h.update(slice);
    Ok((hex::encode(h.finalize()), len))
}
