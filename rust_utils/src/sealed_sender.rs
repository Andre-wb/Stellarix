//! Sealed-sender pseudonym.
//!
//! Mirrors app/security/sealed_sender.py:
//!   sender_pseudo = BLAKE2b-64(key=secret, data=room_id || ":" || sender_id)
//!
//! Called on every outgoing message — Python version takes ~30 µs per
//! call (BLAKE2b init + finalize in the stdlib). Rust version is ~1 µs
//! and releases the GIL via py.allow_threads in batch paths.

use blake2::{Blake2bMac, digest::{KeyInit, Update, FixedOutput}};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

/// Compute per-room pseudonym for a sender. Bit-exact match for the
/// Python implementation in app/security/sealed_sender.py:
///     BLAKE2b(data = room_id_be8 || user_id_be8,
///             key  = 32-byte SEALED_SENDER_SECRET,
///             digest_size = 32)   → 64-char lowercase hex
#[pyfunction]
pub fn compute_sender_pseudo(secret: &[u8], room_id: i64, sender_id: i64) -> PyResult<String> {
    if secret.len() != 32 {
        return Err(PyValueError::new_err(format!(
            "secret must be 32 bytes, got {}", secret.len()
        )));
    }
    // 32-byte output (matches Python digest_size=32).
    type B = Blake2bMac<blake2::digest::consts::U32>;
    let mut mac = B::new_from_slice(secret)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    // Same layout as Python: big-endian i64 for both fields.
    let mut data = [0u8; 16];
    data[..8].copy_from_slice(&room_id.to_be_bytes());
    data[8..].copy_from_slice(&sender_id.to_be_bytes());
    mac.update(&data);
    Ok(hex::encode(mac.finalize_fixed()))
}

/// Verify that a given pseudo matches expected (room, sender) under the secret.
#[pyfunction]
pub fn verify_sender_pseudo(
    secret: &[u8],
    room_id: i64,
    sender_id: i64,
    pseudo: &str,
) -> PyResult<bool> {
    let expected = compute_sender_pseudo(secret, room_id, sender_id)?;
    // constant-time compare
    let a = expected.as_bytes();
    let b = pseudo.as_bytes();
    if a.len() != b.len() { return Ok(false); }
    use subtle::ConstantTimeEq;
    Ok(a.ct_eq(b).into())
}

/// Batch compute — takes a list of (room_id, sender_id) pairs, releases
/// GIL for the whole loop. For mass-decryption of history.
#[pyfunction]
pub fn compute_sender_pseudo_batch(
    py: Python<'_>,
    secret: &[u8],
    pairs: Vec<(i64, i64)>,
) -> PyResult<Vec<String>> {
    if secret.len() != 32 {
        return Err(PyValueError::new_err("secret must be 32 bytes"));
    }
    let secret = secret.to_vec();
    py.allow_threads(move || {
        let mut out = Vec::with_capacity(pairs.len());
        type B = Blake2bMac<blake2::digest::consts::U32>;
        for (r, s) in pairs {
            let mut mac = B::new_from_slice(&secret).unwrap();
            let mut data = [0u8; 16];
            data[..8].copy_from_slice(&r.to_be_bytes());
            data[8..].copy_from_slice(&s.to_be_bytes());
            mac.update(&data);
            out.push(hex::encode(mac.finalize_fixed()));
        }
        Ok(out)
    })
}
