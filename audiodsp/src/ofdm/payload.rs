use std::io::Read;

use chacha20poly1305::aead::{Aead, KeyInit, Payload};
use chacha20poly1305::{ChaCha20Poly1305, Key, Nonce};

const FLAG_COMPRESSED: u8 = 1;
const FLAG_ENCRYPTED: u8 = 2;
const NONCE_LEN: usize = 12;
const TAG_LEN: usize = 16;
const MAX_DECODED: usize = 32 * 1024 * 1024;
const ZSTD_LEVEL: i32 = 3;

pub(crate) fn pack(data: &[u8], key: Option<&[u8; 32]>) -> Vec<u8> {
    let compressed = zstd::stream::encode_all(data, ZSTD_LEVEL).ok();
    let (body, mut flags) = match compressed {
        Some(c) if c.len() < data.len() => (c, FLAG_COMPRESSED),
        _ => (data.to_vec(), 0),
    };
    match key {
        None => {
            let mut out = Vec::with_capacity(1 + body.len());
            out.push(flags);
            out.extend_from_slice(&body);
            out
        }
        Some(k) => {
            flags |= FLAG_ENCRYPTED;
            let cipher = ChaCha20Poly1305::new(Key::from_slice(k));
            let mut nonce = [0u8; NONCE_LEN];
            getrandom::getrandom(&mut nonce).expect("os rng");
            let ct = cipher
                .encrypt(
                    Nonce::from_slice(&nonce),
                    Payload {
                        msg: &body,
                        aad: &[flags],
                    },
                )
                .expect("aead encrypt");
            let mut out = Vec::with_capacity(1 + NONCE_LEN + ct.len());
            out.push(flags);
            out.extend_from_slice(&nonce);
            out.extend_from_slice(&ct);
            out
        }
    }
}

pub(crate) fn unpack(data: &[u8], key: Option<&[u8; 32]>) -> Option<Vec<u8>> {
    let (&flags, rest) = data.split_first()?;
    if flags & !(FLAG_COMPRESSED | FLAG_ENCRYPTED) != 0 {
        return None;
    }
    let encrypted = flags & FLAG_ENCRYPTED != 0;
    if encrypted != key.is_some() {
        return None;
    }
    let body = if encrypted {
        if rest.len() < NONCE_LEN + TAG_LEN {
            return None;
        }
        let (nonce, ct) = rest.split_at(NONCE_LEN);
        let cipher = ChaCha20Poly1305::new(Key::from_slice(key?));
        cipher
            .decrypt(
                Nonce::from_slice(nonce),
                Payload {
                    msg: ct,
                    aad: &[flags],
                },
            )
            .ok()?
    } else {
        rest.to_vec()
    };
    if flags & FLAG_COMPRESSED != 0 {
        let mut out = Vec::new();
        let dec = zstd::stream::Decoder::new(&body[..]).ok()?;
        dec.take(MAX_DECODED as u64 + 1).read_to_end(&mut out).ok()?;
        if out.len() > MAX_DECODED {
            return None;
        }
        Some(out)
    } else {
        Some(body)
    }
}

#[cfg(test)]
mod tests {
    use super::{pack, unpack};

    #[test]
    fn plain_roundtrip_incompressible() {
        let data: Vec<u8> = (0..64u32).map(|i| (i * 2654435761 >> 24) as u8).collect();
        let packed = pack(&data, None);
        assert_eq!(packed[0] & 2, 0);
        assert_eq!(unpack(&packed, None).unwrap(), data);
    }

    #[test]
    fn compression_shrinks_repetitive_data() {
        let data = vec![7u8; 10000];
        let packed = pack(&data, None);
        assert_eq!(packed[0] & 1, 1);
        assert!(packed.len() < 200, "packed {}", packed.len());
        assert_eq!(unpack(&packed, None).unwrap(), data);
    }

    #[test]
    fn encrypted_roundtrip_and_wrong_key_fails() {
        let data = b"secret payload".to_vec();
        let key = [42u8; 32];
        let packed = pack(&data, Some(&key));
        assert_eq!(packed[0] & 2, 2);
        assert_eq!(unpack(&packed, Some(&key)).unwrap(), data);
        let wrong = [43u8; 32];
        assert!(unpack(&packed, Some(&wrong)).is_none());
        assert!(unpack(&packed, None).is_none());
    }

    #[test]
    fn plaintext_rejected_when_key_expected() {
        let data = b"plain".to_vec();
        let packed = pack(&data, None);
        let key = [1u8; 32];
        assert!(unpack(&packed, Some(&key)).is_none());
    }
}
