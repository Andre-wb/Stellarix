use crate::consts::{PKT_CHUNK, PKT_NPARITY, PREAMBLE};
use crate::crc::crc32;
use crate::rs::rs_encode_msg;

pub(crate) fn build_packets(payload: &[u8]) -> Vec<Vec<u8>> {
    let len = payload.len();
    let mut with_len = vec![len as u8];
    with_len.extend_from_slice(payload);
    let crc = crc32(&with_len);
    let mut with_crc = with_len.clone();
    with_crc.push(((crc >> 24) & 0xFF) as u8);
    with_crc.push(((crc >> 16) & 0xFF) as u8);
    with_crc.push(((crc >> 8) & 0xFF) as u8);
    with_crc.push((crc & 0xFF) as u8);
    let total = (with_crc.len() + PKT_CHUNK - 1) / PKT_CHUNK;
    let mut packets = vec![];
    for seq in 0..total {
        let mut chunk = vec![];
        for i in 0..PKT_CHUNK {
            let idx = seq * PKT_CHUNK + i;
            chunk.push(if idx < with_crc.len() { with_crc[idx] } else { 0 });
        }
        let mut data = vec![seq as u8, total as u8, with_crc.len() as u8];
        data.extend_from_slice(&chunk);
        packets.push(rs_encode_msg(&data, PKT_NPARITY));
    }
    packets
}

pub(crate) fn packet_to_bits(body: &[u8]) -> Vec<u8> {
    let mut bits: Vec<u8> = PREAMBLE.to_vec();
    for &byte in body {
        for i in (0..8).rev() {
            bits.push((byte >> i) & 1);
        }
    }
    bits
}
