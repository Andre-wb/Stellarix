//! Double Ratchet chain-key advance + AES-GCM wrap.
//!
//! State lives in Python (so the existing Python DR code keeps owning
//! persistence). Each message invokes this hot loop:
//!   - advance chain-key via HKDF-SHA256
//!   - derive message key
//!   - encrypt plaintext with AES-256-GCM using the derived key
//!
//! Python version does ~200 µs per message because of HMAC-SHA256
//! reconstruction + AES-GCM via cryptography's PyOpenSSL binding.
//! Here we do it in pure Rust with `hkdf` + `aes-gcm` → ~5 µs.
//!
//! KDF labels chosen to match app/security/double_ratchet.py constants.

use aes_gcm::{Aes256Gcm, Key, Nonce, aead::{Aead, KeyInit}};
use hkdf::Hkdf;
use hmac::{Hmac, Mac};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::PyBytes;
use sha2::Sha256;

// Signal-standard single-byte labels, matching app/security/double_ratchet.py:
//   new_chain_key = HMAC(ck, 0x02)
//   message_key   = HMAC(ck, 0x01)
const CHAIN_LABEL:   &[u8] = &[0x02];
const MSG_KEY_LABEL: &[u8] = &[0x01];


/// Advance the chain-key by one step. Input 32 bytes, output 32 bytes.
/// `next_chain = HMAC-SHA256(chain, CHAIN_LABEL)`.
#[pyfunction]
pub fn ratchet_advance_chain(py: Python<'_>, chain_key: &[u8]) -> PyResult<Py<PyBytes>> {
    if chain_key.len() != 32 {
        return Err(PyValueError::new_err("chain_key must be 32 bytes"));
    }
    let ck = chain_key.to_vec();
    let next = py.allow_threads(move || {
        type HmacSha256 = Hmac<Sha256>;
        let mut h = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h.update(CHAIN_LABEL);
        let out = h.finalize().into_bytes();
        out.to_vec()
    });
    Ok(PyBytes::new(py, &next).into())
}

/// Derive a 32-byte message key from the current chain-key.
/// `msg_key = HMAC-SHA256(chain, MSG_KEY_LABEL)`.
#[pyfunction]
pub fn ratchet_message_key(py: Python<'_>, chain_key: &[u8]) -> PyResult<Py<PyBytes>> {
    if chain_key.len() != 32 {
        return Err(PyValueError::new_err("chain_key must be 32 bytes"));
    }
    let ck = chain_key.to_vec();
    let mk = py.allow_threads(move || {
        type HmacSha256 = Hmac<Sha256>;
        let mut h = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h.update(MSG_KEY_LABEL);
        let out = h.finalize().into_bytes();
        out.to_vec()
    });
    Ok(PyBytes::new(py, &mk).into())
}

/// Encrypt a message in one call: derives msg-key from chain, encrypts
/// plaintext with AES-GCM using a fresh 12-byte nonce, returns
/// (ciphertext || tag, nonce, next_chain_key).
#[pyfunction]
pub fn ratchet_encrypt_step(
    py: Python<'_>,
    chain_key: &[u8],
    plaintext: &[u8],
    associated_data: Option<&[u8]>,
) -> PyResult<(Py<PyBytes>, Py<PyBytes>, Py<PyBytes>)> {
    if chain_key.len() != 32 {
        return Err(PyValueError::new_err("chain_key must be 32 bytes"));
    }
    let ck = chain_key.to_vec();
    let pt = plaintext.to_vec();
    let ad = associated_data.map(|x| x.to_vec()).unwrap_or_default();

    let (ct, nonce_bytes, next_chain) = py.allow_threads(move || {
        type HmacSha256 = Hmac<Sha256>;

        // Derive message key
        let mut h = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h.update(MSG_KEY_LABEL);
        let mk_arr = h.finalize().into_bytes();

        // Advance chain
        let mut h2 = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h2.update(CHAIN_LABEL);
        let next = h2.finalize().into_bytes();

        // AES-GCM encrypt
        use rand::RngCore;
        let mut nonce = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut nonce);
        let key = Key::<Aes256Gcm>::from_slice(&mk_arr);
        let cipher = Aes256Gcm::new(key);
        let payload = aes_gcm::aead::Payload { msg: &pt, aad: &ad };
        let ct_vec = cipher.encrypt(Nonce::from_slice(&nonce), payload)
            .map_err(|_| "encrypt failed")?;
        Ok::<_, &'static str>((ct_vec, nonce.to_vec(), next.to_vec()))
    }).map_err(|e| PyValueError::new_err(e))?;

    Ok((
        PyBytes::new(py, &ct).into(),
        PyBytes::new(py, &nonce_bytes).into(),
        PyBytes::new(py, &next_chain).into(),
    ))
}

/// Decrypt counterpart — same KDF, caller provides nonce + ciphertext.
#[pyfunction]
pub fn ratchet_decrypt_step(
    py: Python<'_>,
    chain_key: &[u8],
    nonce: &[u8],
    ciphertext: &[u8],
    associated_data: Option<&[u8]>,
) -> PyResult<(Py<PyBytes>, Py<PyBytes>)> {
    if chain_key.len() != 32 {
        return Err(PyValueError::new_err("chain_key must be 32 bytes"));
    }
    if nonce.len() != 12 {
        return Err(PyValueError::new_err("nonce must be 12 bytes"));
    }
    let ck = chain_key.to_vec();
    let n  = nonce.to_vec();
    let ct = ciphertext.to_vec();
    let ad = associated_data.map(|x| x.to_vec()).unwrap_or_default();

    let (pt, next_chain) = py.allow_threads(move || {
        type HmacSha256 = Hmac<Sha256>;

        let mut h = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h.update(MSG_KEY_LABEL);
        let mk_arr = h.finalize().into_bytes();

        let mut h2 = <HmacSha256 as Mac>::new_from_slice(&ck).unwrap();
        h2.update(CHAIN_LABEL);
        let next = h2.finalize().into_bytes();

        let key = Key::<Aes256Gcm>::from_slice(&mk_arr);
        let cipher = Aes256Gcm::new(key);
        let payload = aes_gcm::aead::Payload { msg: &ct, aad: &ad };
        let pt_vec = cipher.decrypt(Nonce::from_slice(&n), payload)
            .map_err(|_| "decrypt/auth failed")?;
        Ok::<_, &'static str>((pt_vec, next.to_vec()))
    }).map_err(|e| PyValueError::new_err(e))?;

    Ok((
        PyBytes::new(py, &pt).into(),
        PyBytes::new(py, &next_chain).into(),
    ))
}

/// Fresh root-key derivation from a shared secret using HKDF-SHA256.
#[pyfunction]
pub fn ratchet_root_kdf(py: Python<'_>, shared_secret: &[u8], info: &[u8]) -> PyResult<Py<PyBytes>> {
    let ss = shared_secret.to_vec();
    let inf = info.to_vec();
    let out = py.allow_threads(move || {
        let hk = Hkdf::<Sha256>::new(None, &ss);
        let mut okm = [0u8; 32];
        hk.expand(&inf, &mut okm).unwrap();
        okm.to_vec()
    });
    Ok(PyBytes::new(py, &out).into())
}


/// Bit-compatible Python `kdf_rk`: HKDF-SHA256 with salt=rk, IKM=dh_out,
/// info=b"vortex-double-ratchet", length=64 → (new_root_key, new_chain_key).
#[pyfunction]
pub fn ratchet_kdf_rk(
    py: Python<'_>,
    rk: &[u8],
    dh_out: &[u8],
) -> PyResult<(Py<PyBytes>, Py<PyBytes>)> {
    if rk.len() != 32 {
        return Err(PyValueError::new_err("rk must be 32 bytes"));
    }
    if dh_out.len() != 32 {
        return Err(PyValueError::new_err("dh_out must be 32 bytes"));
    }
    let rk_v = rk.to_vec();
    let dh_v = dh_out.to_vec();
    let (root, chain) = py.allow_threads(move || {
        let hk = Hkdf::<Sha256>::new(Some(&rk_v), &dh_v);
        let mut okm = [0u8; 64];
        hk.expand(b"vortex-double-ratchet", &mut okm).unwrap();
        let mut root = [0u8; 32];
        let mut chain = [0u8; 32];
        root.copy_from_slice(&okm[..32]);
        chain.copy_from_slice(&okm[32..]);
        (root, chain)
    });
    Ok((
        PyBytes::new(py, &root).into(),
        PyBytes::new(py, &chain).into(),
    ))
}


/// Bit-compatible Python `kdf_ck`: returns (new_chain_key, message_key).
///   new_ck = HMAC-SHA256(ck, 0x02)
///   mk     = HMAC-SHA256(ck, 0x01)
#[pyfunction]
pub fn ratchet_kdf_ck(py: Python<'_>, ck: &[u8]) -> PyResult<(Py<PyBytes>, Py<PyBytes>)> {
    if ck.len() != 32 {
        return Err(PyValueError::new_err("ck must be 32 bytes"));
    }
    let ck_v = ck.to_vec();
    let (new_ck, mk) = py.allow_threads(move || {
        type H = Hmac<Sha256>;
        let mut h1 = <H as Mac>::new_from_slice(&ck_v).unwrap();
        h1.update(&[0x02]);
        let new_ck = h1.finalize().into_bytes().to_vec();
        let mut h2 = <H as Mac>::new_from_slice(&ck_v).unwrap();
        h2.update(&[0x01]);
        let mk = h2.finalize().into_bytes().to_vec();
        (new_ck, mk)
    });
    Ok((
        PyBytes::new(py, &new_ck).into(),
        PyBytes::new(py, &mk).into(),
    ))
}
