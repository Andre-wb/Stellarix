use super::config::{Modulation, MAX_DATA_SYMBOLS};
use super::util::{bits_to_bytes, push_bits, read_bits};

pub(crate) const HEADER_BITS: usize = 72;
pub(crate) const HEADER_VERSION: u8 = 1;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PacketHeader {
    pub version: u8,
    pub seq: u16,
    pub total: u16,
    pub payload_len: u16,
    pub modulation: Modulation,
    pub n_data_symbols: u8,
}

fn crc8(data: &[u8]) -> u8 {
    let mut crc = 0u8;
    for &b in data {
        crc ^= b;
        for _ in 0..8 {
            crc = if crc & 0x80 != 0 {
                (crc << 1) ^ 0x07
            } else {
                crc << 1
            };
        }
    }
    crc
}

fn pack_fields(h: &PacketHeader, crc: u8) -> Vec<u8> {
    let mut bits = Vec::with_capacity(HEADER_BITS);
    push_bits(&mut bits, h.version as u32, 4);
    push_bits(&mut bits, h.seq as u32, 12);
    push_bits(&mut bits, h.total as u32, 12);
    push_bits(&mut bits, h.payload_len as u32, 16);
    push_bits(&mut bits, h.modulation.id() as u32, 3);
    push_bits(&mut bits, h.n_data_symbols as u32, 8);
    push_bits(&mut bits, crc as u32, 8);
    push_bits(&mut bits, 0, 9);
    bits
}

pub(crate) fn header_bits(h: &PacketHeader) -> Vec<u8> {
    let plain = pack_fields(h, 0);
    let crc = crc8(&bits_to_bytes(&plain));
    pack_fields(h, crc)
}

pub(crate) fn parse_header_bits(bits: &[u8]) -> Option<PacketHeader> {
    if bits.len() < HEADER_BITS {
        return None;
    }
    let mut pos = 0usize;
    let version = read_bits(bits, &mut pos, 4) as u8;
    let seq = read_bits(bits, &mut pos, 12) as u16;
    let total = read_bits(bits, &mut pos, 12) as u16;
    let payload_len = read_bits(bits, &mut pos, 16) as u16;
    let modulation = Modulation::from_id(read_bits(bits, &mut pos, 3) as u8)?;
    let n_data_symbols = read_bits(bits, &mut pos, 8) as u8;
    let crc = read_bits(bits, &mut pos, 8) as u8;
    let hdr = PacketHeader {
        version,
        seq,
        total,
        payload_len,
        modulation,
        n_data_symbols,
    };
    let plain = pack_fields(&hdr, 0);
    if crc8(&bits_to_bytes(&plain)) != crc {
        return None;
    }
    if version != HEADER_VERSION {
        return None;
    }
    if total == 0 || seq >= total {
        return None;
    }
    if n_data_symbols == 0 || n_data_symbols as usize > MAX_DATA_SYMBOLS {
        return None;
    }
    Some(hdr)
}

pub(crate) fn header_from_soft(soft: &[f32]) -> Option<PacketHeader> {
    let mut acc = [0f64; HEADER_BITS];
    for (i, &s) in soft.iter().enumerate() {
        acc[i % HEADER_BITS] += s as f64;
    }
    let bits: Vec<u8> = acc.iter().map(|&a| if a < 0.0 { 1 } else { 0 }).collect();
    parse_header_bits(&bits)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_header() -> PacketHeader {
        PacketHeader {
            version: HEADER_VERSION,
            seq: 2,
            total: 5,
            payload_len: 1234,
            modulation: Modulation::Qam16,
            n_data_symbols: 17,
        }
    }

    #[test]
    fn header_roundtrip() {
        let h = sample_header();
        let bits = header_bits(&h);
        assert_eq!(bits.len(), HEADER_BITS);
        assert_eq!(parse_header_bits(&bits), Some(h));
    }

    #[test]
    fn corrupted_header_rejected() {
        let h = sample_header();
        for i in 0..HEADER_BITS - 9 {
            let mut bits = header_bits(&h);
            bits[i] ^= 1;
            assert_ne!(parse_header_bits(&bits), Some(h.clone()), "bit {}", i);
        }
    }

    #[test]
    fn soft_majority_survives_minority_flips() {
        let h = sample_header();
        let bits = header_bits(&h);
        let mut soft: Vec<f32> = (0..480)
            .map(|i| if bits[i % HEADER_BITS] == 1 { -1.0 } else { 1.0 })
            .collect();
        for i in (0..480).step_by(5) {
            soft[i] = -soft[i];
        }
        assert_eq!(header_from_soft(&soft), Some(h));
    }
}
