use pyo3::prelude::*;

mod messages;
pub use messages::{
    hash::{hash_message, generate_key},
    crypt::{encrypt_message, decrypt_message},
    ChatStats
};

mod auth;
use auth::{
    passwords::{hash_password, verify_password},
    tokens::{hash_token, verify_token},
};

mod udp_broadcast;
use udp_broadcast::discovery::{get_peers, start_discovery};

mod crypto;
use crypto::handshake::{
    derive_session_key, generate_keypair
};

pub mod bmp;
use bmp::pybridge::*;

// New hot-path modules — each exposes a handful of #[pyfunction]s the
// Python side drops in as a replacement for its current slow path.
mod sealed_sender;
use sealed_sender::{compute_sender_pseudo, verify_sender_pseudo, compute_sender_pseudo_batch};
mod canonical_json;
use canonical_json::{canonical_json as canonical_json_fn, sign_canonical};
mod ratchet_kdf;
use ratchet_kdf::{ratchet_advance_chain, ratchet_message_key,
                  ratchet_encrypt_step, ratchet_decrypt_step, ratchet_root_kdf,
                  ratchet_kdf_rk, ratchet_kdf_ck};
mod integrity_walk;
use integrity_walk::{sha256_manifest_walk, verify_manifest};
mod steganography;
use steganography::{steg_embed_png, steg_extract_png, steg_embed_bytes};
mod metadata_padding;
use metadata_padding::{pad_to_bucket, unpad_from_bucket, pad_bucket_for};
mod batch_verify;
use batch_verify::{verify_signature as ed_verify, batch_verify as ed_batch_verify};
mod chunk_hash;
use chunk_hash::{sha256_hex, sha256_concat_hex, sha256_combine_hex, sha256_stream};


#[pymodule]
fn vortex_chat(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Existing crypto
    m.add_function(wrap_pyfunction!(hash_message, m)?)?;
    m.add_function(wrap_pyfunction!(generate_key, m)?)?;
    m.add_function(wrap_pyfunction!(encrypt_message, m)?)?;
    m.add_function(wrap_pyfunction!(decrypt_message, m)?)?;
    m.add_function(wrap_pyfunction!(hash_password, m)?)?;
    m.add_function(wrap_pyfunction!(verify_password, m)?)?;
    m.add_function(wrap_pyfunction!(hash_token, m)?)?;
    m.add_function(wrap_pyfunction!(verify_token, m)?)?;
    m.add_function(wrap_pyfunction!(start_discovery, m)?)?;
    m.add_function(wrap_pyfunction!(get_peers, m)?)?;
    m.add_function(wrap_pyfunction!(generate_keypair, m)?)?;
    m.add_function(wrap_pyfunction!(derive_session_key, m)?)?;
    m.add_class::<ChatStats>()?;

    // BMP (Blind Mailbox Protocol) — high-performance Rust implementation
    m.add_function(wrap_pyfunction!(bmp_deposit, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_fetch, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_fetch_batch, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_gc, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_stats, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_compute_mailbox_id, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_compute_mailbox_ids, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_pair_jitter, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_set_room_secret, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_get_room_secret, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_remove_room_secret, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_deposit_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_check_rate, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_check_rate_fast, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_wake_category, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_start_gc, m)?)?;
    m.add_function(wrap_pyfunction!(bmp_benchmark, m)?)?;

    // Sealed-sender pseudonym
    m.add_function(wrap_pyfunction!(compute_sender_pseudo, m)?)?;
    m.add_function(wrap_pyfunction!(verify_sender_pseudo, m)?)?;
    m.add_function(wrap_pyfunction!(compute_sender_pseudo_batch, m)?)?;

    // Canonical JSON + ed25519 signing
    m.add_function(wrap_pyfunction!(canonical_json_fn, m)?)?;
    m.add_function(wrap_pyfunction!(sign_canonical, m)?)?;

    // Double Ratchet chain KDF + AES-GCM wrap
    m.add_function(wrap_pyfunction!(ratchet_advance_chain, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_message_key, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_encrypt_step, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_decrypt_step, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_root_kdf, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_kdf_rk, m)?)?;
    m.add_function(wrap_pyfunction!(ratchet_kdf_ck, m)?)?;

    // Integrity manifest walk (parallel SHA-256)
    m.add_function(wrap_pyfunction!(sha256_manifest_walk, m)?)?;
    m.add_function(wrap_pyfunction!(verify_manifest, m)?)?;

    // Steganography LSB
    m.add_function(wrap_pyfunction!(steg_embed_png, m)?)?;
    m.add_function(wrap_pyfunction!(steg_extract_png, m)?)?;
    m.add_function(wrap_pyfunction!(steg_embed_bytes, m)?)?;

    // Metadata padding
    m.add_function(wrap_pyfunction!(pad_to_bucket, m)?)?;
    m.add_function(wrap_pyfunction!(unpad_from_bucket, m)?)?;
    m.add_function(wrap_pyfunction!(pad_bucket_for, m)?)?;

    // Ed25519 single + batch verify
    m.add_function(wrap_pyfunction!(ed_verify, m)?)?;
    m.add_function(wrap_pyfunction!(ed_batch_verify, m)?)?;

    // Resumable-upload chunk hashing
    m.add_function(wrap_pyfunction!(sha256_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_concat_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_combine_hex, m)?)?;
    m.add_function(wrap_pyfunction!(sha256_stream, m)?)?;

    m.add("VERSION", env!("CARGO_PKG_VERSION"))?;
    m.add("KEY_SIZE", 32usize)?;
    m.add("NONCE_SIZE", 12usize)?;
    Ok(())
}