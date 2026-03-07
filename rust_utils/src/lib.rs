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


#[pymodule]
fn vortex_chat(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
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
    m.add("VERSION", env!("CARGO_PKG_VERSION"))?;
    m.add("KEY_SIZE", 32usize)?;
    m.add("NONCE_SIZE", 12usize)?;
    Ok(())
}