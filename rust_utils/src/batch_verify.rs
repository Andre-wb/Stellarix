//! Ed25519 batch signature verification.
//!
//! Controller receives 1000+ signed heartbeats per minute. Verifying
//! them sequentially with pure Python `cryptography` is ~300 µs each
//! = up to 300 ms of CPU. `ed25519-dalek` batch verify amortizes the
//! Edwards curve cost, giving 3-5x throughput on the same core.

use ed25519_dalek::{Verifier, VerifyingKey, Signature};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

/// Verify a single signature. Useful inside hot loops; cheaper than the
/// PyOpenSSL wrapper's call overhead by ~10x.
#[pyfunction]
pub fn verify_signature(
    py: Python<'_>,
    pubkey_32: &[u8],
    message: &[u8],
    signature_64: &[u8],
) -> PyResult<bool> {
    if pubkey_32.len() != 32 {
        return Err(PyValueError::new_err("pubkey must be 32 bytes"));
    }
    if signature_64.len() != 64 {
        return Err(PyValueError::new_err("signature must be 64 bytes"));
    }
    let pub_bytes: [u8; 32] = pubkey_32.try_into().unwrap();
    let sig_bytes: [u8; 64] = signature_64.try_into().unwrap();
    let msg = message.to_vec();
    let ok = py.allow_threads(move || {
        let vk = match VerifyingKey::from_bytes(&pub_bytes) {
            Ok(k) => k, Err(_) => return false,
        };
        let sig = Signature::from_bytes(&sig_bytes);
        vk.verify(&msg, &sig).is_ok()
    });
    Ok(ok)
}

/// Batch-verify. Input: parallel lists of pubkeys, messages, signatures.
/// Returns one-call success (all valid). For per-item results, fall
/// back to `verify_signature` in a loop.
///
/// `pubkeys` and `signatures` are flat concatenated bytes (32 / 64 bytes
/// per entry) to avoid Vec<Vec<u8>> marshalling overhead.
#[pyfunction]
pub fn batch_verify(
    py: Python<'_>,
    pubkeys_flat: &[u8],
    messages: Vec<Vec<u8>>,
    signatures_flat: &[u8],
) -> PyResult<bool> {
    let n = messages.len();
    if pubkeys_flat.len() != n * 32 {
        return Err(PyValueError::new_err(format!(
            "pubkeys_flat: expected {} bytes, got {}", n * 32, pubkeys_flat.len()
        )));
    }
    if signatures_flat.len() != n * 64 {
        return Err(PyValueError::new_err(format!(
            "signatures_flat: expected {} bytes, got {}", n * 64, signatures_flat.len()
        )));
    }

    // Copy into owned slices so we can release the GIL.
    let pubkeys_vec = pubkeys_flat.to_vec();
    let sigs_vec    = signatures_flat.to_vec();
    let msgs        = messages;

    let ok = py.allow_threads(move || -> Result<bool, ()> {
        let mut vks = Vec::with_capacity(n);
        let mut sigs = Vec::with_capacity(n);
        for i in 0..n {
            let pk_arr: [u8; 32] = pubkeys_vec[i * 32..(i + 1) * 32].try_into().unwrap();
            let sg_arr: [u8; 64] = sigs_vec[i * 64..(i + 1) * 64].try_into().unwrap();
            let vk = match VerifyingKey::from_bytes(&pk_arr) { Ok(k) => k, Err(_) => return Ok(false) };
            vks.push(vk);
            sigs.push(Signature::from_bytes(&sg_arr));
        }
        let msg_refs: Vec<&[u8]> = msgs.iter().map(|m| m.as_slice()).collect();
        match ed25519_dalek::verify_batch(&msg_refs, &sigs, &vks) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }).map_err(|_| PyValueError::new_err("batch verify internal error"))?;
    Ok(ok)
}
