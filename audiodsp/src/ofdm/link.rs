use std::collections::HashMap;

use crate::crc::crc32;

use super::config::{OfdmConfig, MAX_DATA_SYMBOLS};
use super::demodulator::{Demodulator, PacketRx};
use super::fec;
use super::framing::{PacketHeader, HEADER_VERSION};
use super::modulator::Modulator;
use super::payload::{pack, unpack};
use super::sync::{chirp, find_chirp, refine_by_cp};
use super::util::{bits_to_bytes, bytes_to_bits};

pub const CHIRP_THRESHOLD: f32 = 0.35;
pub const MAX_PACKETS: usize = 4095;

pub fn max_packet_payload(cfg: &OfdmConfig) -> usize {
    let cap_bytes = MAX_DATA_SYMBOLS * cfg.bits_per_symbol() / 8;
    let mut l = cap_bytes.saturating_sub(4);
    while l > 0 {
        if fec::FecLayout::for_len(l + 4).coded_len() <= cap_bytes {
            return l;
        }
        l -= 1;
    }
    0
}

pub fn pack_payload(payload: &[u8], key: Option<&[u8; 32]>) -> Vec<u8> {
    pack(payload, key)
}

pub fn unpack_payload(packed: &[u8], key: Option<&[u8; 32]>) -> Option<Vec<u8>> {
    unpack(packed, key)
}

pub fn packed_chunk_count(packed_len: usize, cfg: &OfdmConfig) -> usize {
    let max_chunk = max_packet_payload(cfg).max(1);
    (packed_len + max_chunk - 1) / max_chunk
}

pub fn transmission_lead(cfg: &OfdmConfig) -> usize {
    cfg.fs as usize / 4
}

pub fn transmission_gap(cfg: &OfdmConfig) -> usize {
    cfg.fs as usize / 10
}

fn n_symbols_for(cfg: &OfdmConfig, header: &PacketHeader) -> usize {
    let coded_bits = fec::FecLayout::for_len(header.payload_len as usize + 4).coded_len() * 8;
    let bps = cfg.n_data_carriers() * header.modulation.bits_per_carrier();
    (coded_bits + bps - 1) / bps
}

pub fn encode_transmission(payload: &[u8], cfg: &OfdmConfig) -> Vec<f32> {
    encode_packed(&pack(payload, None), cfg)
}

pub fn encode_transmission_encrypted(
    payload: &[u8],
    cfg: &OfdmConfig,
    key: &[u8; 32],
) -> Vec<f32> {
    encode_packed(&pack(payload, Some(key)), cfg)
}

fn build_one(
    modulator: &mut Modulator,
    chunk: &[u8],
    seq: usize,
    total: usize,
    cfg: &OfdmConfig,
) -> Vec<f32> {
    let mut data = chunk.to_vec();
    data.extend_from_slice(&crc32(chunk).to_be_bytes());
    let coded = fec::encode(&data);
    let bits = bytes_to_bits(&coded);
    let bps = cfg.bits_per_symbol();
    let n_sym = (bits.len() + bps - 1) / bps;
    assert!(n_sym <= MAX_DATA_SYMBOLS);
    let hdr = PacketHeader {
        version: HEADER_VERSION,
        seq: seq as u16,
        total: total as u16,
        payload_len: chunk.len() as u16,
        modulation: cfg.modulation,
        n_data_symbols: n_sym as u8,
    };
    modulator.build_packet(&hdr, &bits)
}

pub fn encode_one_packet(packed: &[u8], seq: usize, cfg: &OfdmConfig) -> Option<Vec<f32>> {
    let total = packed_chunk_count(packed.len(), cfg);
    if seq >= total {
        return None;
    }
    let max_chunk = max_packet_payload(cfg).max(1);
    let start = seq * max_chunk;
    let end = (start + max_chunk).min(packed.len());
    let mut modulator = Modulator::new(cfg.clone());
    Some(build_one(
        &mut modulator,
        &packed[start..end],
        seq,
        total,
        cfg,
    ))
}

fn encode_packed(packed: &[u8], cfg: &OfdmConfig) -> Vec<f32> {
    let max_chunk = max_packet_payload(cfg).max(1);
    let chunks: Vec<&[u8]> = packed.chunks(max_chunk).collect();
    let total = chunks.len();
    assert!(total <= MAX_PACKETS, "payload too large");
    let mut modulator = Modulator::new(cfg.clone());
    let lead = transmission_lead(cfg);
    let inter = transmission_gap(cfg);
    let mut out = vec![0f32; lead];
    for (seq, chunk) in chunks.iter().enumerate() {
        out.extend(build_one(&mut modulator, chunk, seq, total, cfg));
        out.extend(std::iter::repeat(0f32).take(inter));
    }
    out.extend(std::iter::repeat(0f32).take(lead));
    out
}

fn finish_packet(cfg: &OfdmConfig, r: &PacketRx) -> Option<Vec<u8>> {
    let hdr = &r.header;
    if hdr.n_data_symbols as usize != n_symbols_for(cfg, hdr) {
        return None;
    }
    let data_len = hdr.payload_len as usize + 4;
    let l = fec::FecLayout::for_len(data_len);
    let coded_bits = l.coded_len() * 8;
    if r.bits.len() < coded_bits {
        return None;
    }
    let coded = bits_to_bytes(&r.bits[..coded_bits]);
    let mut bad = vec![false; l.coded_len()];
    for &b in &r.bad_bytes {
        if b < bad.len() {
            bad[b] = true;
        }
    }
    let data = fec::decode(&coded, data_len, &bad)?;
    let payload = &data[..hdr.payload_len as usize];
    let expect = u32::from_be_bytes([
        data[data_len - 4],
        data[data_len - 3],
        data[data_len - 2],
        data[data_len - 1],
    ]);
    if crc32(payload) != expect {
        return None;
    }
    Some(payload.to_vec())
}

fn resample_segment(rx: &[f32], seg_start: usize, out_len: usize, eps: f64) -> Vec<f32> {
    let mut seg = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let s = seg_start as f64 + i as f64 * (1.0 + eps);
        let i0 = s.floor() as usize;
        let frac = (s - i0 as f64) as f32;
        let a = rx.get(i0).copied().unwrap_or(0.0);
        let b = rx.get(i0 + 1).copied().unwrap_or(0.0);
        seg.push(a + (b - a) * frac);
    }
    seg
}

fn attempt_resampled(
    rx: &[f32],
    train: usize,
    demod: &mut Demodulator,
    cfg: &OfdmConfig,
    eps: f64,
) -> Option<(PacketHeader, Vec<u8>)> {
    let seg_start = train.saturating_sub(cfg.cp_len);
    let nominal = cfg.cp_len + (2 + MAX_DATA_SYMBOLS) * cfg.symbol_samples() + 4 * cfg.cp_len;
    let seg = resample_segment(rx, seg_start, nominal, eps);
    let approx = ((train - seg_start) as f64 / (1.0 + eps)).round() as usize;
    let (train2, _) = refine_by_cp(&seg, approx, cfg);
    let r = demod.receive_packet_full(&seg, train2)?;
    let payload = finish_packet(cfg, &r)?;
    Some((r.header, payload))
}

fn try_packet(
    rx: &[f32],
    train: usize,
    demod: &mut Demodulator,
    cfg: &OfdmConfig,
) -> Option<(PacketHeader, Vec<u8>)> {
    let first = demod.receive_packet_full(rx, train);
    let mut eps_hint = None;
    if let Some(r) = first {
        if let Some(p) = finish_packet(cfg, &r) {
            return Some((r.header, p));
        }
        if r.sfo.abs() >= 1e-4 {
            eps_hint = Some(r.sfo);
        }
    }
    let mut candidates: Vec<f64> = vec![];
    if let Some(e) = eps_hint {
        candidates.push(e);
    }
    for ppm in [500.0f64, 1000.0, 1500.0, 2000.0, 2500.0] {
        candidates.push(ppm * 1e-6);
        candidates.push(-ppm * 1e-6);
    }
    for eps in candidates {
        if let Some(ok) = attempt_resampled(rx, train, demod, cfg, eps) {
            return Some(ok);
        }
    }
    None
}

pub struct DecodeReport {
    pub payload: Option<Vec<u8>>,
    pub have: usize,
    pub total: Option<usize>,
}

pub fn max_total_seconds(cfg: &OfdmConfig) -> f32 {
    let pkt = cfg.chirp_len()
        + cfg.gap_len()
        + (2 + MAX_DATA_SYMBOLS) * cfg.symbol_samples()
        + cfg.gap_len();
    let lead = transmission_lead(cfg);
    let inter = transmission_gap(cfg);
    (2 * lead + pkt + inter) as f32 / cfg.fs as f32
}

pub fn decode_transmission_report(
    rx: &[f32],
    cfg: &OfdmConfig,
    key: Option<&[u8; 32]>,
) -> DecodeReport {
    let template = chirp(cfg);
    let mut demod = Demodulator::new(cfg.clone());
    let sym_len = cfg.symbol_samples();
    let mut cursor = 0usize;
    let mut total: Option<usize> = None;
    let mut parts: HashMap<usize, Vec<u8>> = HashMap::new();
    while cursor + template.len() < rx.len() {
        let found = match find_chirp(&rx[cursor..], &template, CHIRP_THRESHOLD) {
            Some(p) => cursor + p,
            None => break,
        };
        let approx = found + cfg.chirp_len() + cfg.gap_len();
        let (train, _cfo) = refine_by_cp(rx, approx, cfg);
        let mut advance = cfg.chirp_len();
        if let Some((hdr, payload)) = try_packet(rx, train, &mut demod, cfg) {
            if total.is_none() {
                total = Some(hdr.total as usize);
            }
            if Some(hdr.total as usize) == total {
                parts.entry(hdr.seq as usize).or_insert(payload);
            }
            advance = cfg.chirp_len()
                + cfg.gap_len()
                + (2 + hdr.n_data_symbols as usize) * sym_len
                + cfg.gap_len();
            if parts.len() == total.unwrap() {
                break;
            }
        }
        cursor = found + advance;
    }
    let have = parts.len();
    let payload = total.and_then(|t| {
        if parts.len() < t {
            return None;
        }
        let mut out = Vec::new();
        for s in 0..t {
            out.extend_from_slice(parts.get(&s)?);
        }
        unpack(&out, key)
    });
    DecodeReport {
        payload,
        have,
        total,
    }
}

pub fn decode_transmission(rx: &[f32], cfg: &OfdmConfig) -> Option<Vec<u8>> {
    decode_transmission_report(rx, cfg, None).payload
}

pub fn decode_transmission_encrypted(
    rx: &[f32],
    cfg: &OfdmConfig,
    key: &[u8; 32],
) -> Option<Vec<u8>> {
    decode_transmission_report(rx, cfg, Some(key)).payload
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ofdm::util::Prng;

    fn resample(src: &[f32], drift: f64, pad: usize) -> Vec<f32> {
        let body = (src.len() as f64 / (1.0 + drift)).floor() as usize;
        let mut out = vec![0f32; pad + body + 4000];
        for i in 0..body {
            let s = i as f64 * (1.0 + drift);
            let i0 = s.floor() as usize;
            let frac = (s - i0 as f64) as f32;
            let a = *src.get(i0).unwrap_or(&0.0);
            let b = *src.get(i0 + 1).unwrap_or(&0.0);
            out[pad + i] = a + (b - a) * frac;
        }
        out
    }

    #[test]
    fn streamed_packets_match_single_shot() {
        let cfg = OfdmConfig::default_48k();
        let mut rng = Prng::new(11);
        let payload: Vec<u8> = (0..8000).map(|_| (rng.next_u64() & 0xff) as u8).collect();
        let packed = pack_payload(&payload, None);
        let total = packed_chunk_count(packed.len(), &cfg);
        assert!(total > 1, "test needs a multi-packet payload, got {}", total);
        let mut streamed = vec![0f32; transmission_lead(&cfg)];
        for seq in 0..total {
            streamed.extend(encode_one_packet(&packed, seq, &cfg).unwrap());
            streamed.extend(std::iter::repeat(0f32).take(transmission_gap(&cfg)));
        }
        streamed.extend(std::iter::repeat(0f32).take(transmission_lead(&cfg)));
        let single = encode_packed(&packed, &cfg);
        assert_eq!(streamed.len(), single.len());
        assert!(streamed == single, "streamed wave differs from single-shot wave");
        assert!(encode_one_packet(&packed, total, &cfg).is_none());
    }

    #[test]
    fn sfo_tracker_estimates_true_drift() {
        let cfg = OfdmConfig::default_48k();
        let mut rng = Prng::new(5);
        let payload: Vec<u8> = (0..800).map(|_| (rng.next_u64() & 0xff) as u8).collect();
        let tx = encode_transmission(&payload, &cfg);
        let drift = 5e-4;
        let rx = resample(&tx, drift, 900);
        let template = chirp(&cfg);
        let pos = find_chirp(&rx, &template, CHIRP_THRESHOLD).unwrap();
        let approx = pos + cfg.chirp_len() + cfg.gap_len();
        let (train, _) = refine_by_cp(&rx, approx, &cfg);
        let mut demod = Demodulator::new(cfg.clone());
        let r = demod.receive_packet_full(&rx, train).unwrap();
        let expected = 1.0 / (1.0 + drift) - 1.0;
        assert!(
            (r.sfo - expected).abs() < 2e-4,
            "sfo {} expected {}",
            r.sfo,
            expected
        );
        let got = try_packet(&rx, train, &mut demod, &cfg).expect("packet not recovered");
        assert_eq!(unpack(&got.1, None).unwrap(), payload);
    }

    #[test]
    fn raw_ber_low_under_noise() {
        let cfg = OfdmConfig::default_48k();
        let mut rng = Prng::new(77);
        let payload: Vec<u8> = (0..500).map(|_| (rng.next_u64() & 0xff) as u8).collect();
        let tx = encode_transmission(&payload, &cfg);
        let acc: f64 = tx.iter().map(|&v| v as f64 * v as f64).sum();
        let active = tx.iter().filter(|v| v.abs() > 0.0).count();
        let rms = (acc / active as f64).sqrt() as f32;
        let sigma = rms / 10f32.powf(6.0 / 20.0);
        let mut rx = tx.clone();
        for v in rx.iter_mut() {
            *v += (rng.next_f32() * 2.0 - 1.0) * sigma * 1.732;
        }
        let template = chirp(&cfg);
        let pos = find_chirp(&rx, &template, CHIRP_THRESHOLD).unwrap();
        let approx = pos + cfg.chirp_len() + cfg.gap_len();
        let (train, _) = refine_by_cp(&rx, approx, &cfg);
        let mut demod = Demodulator::new(cfg.clone());
        let r = demod.receive_packet_full(&rx, train).unwrap();
        let packed = pack(&payload, None);
        let mut data = packed.clone();
        data.extend_from_slice(&crc32(&packed).to_be_bytes());
        let sent = bytes_to_bits(&fec::encode(&data));
        let errors = sent
            .iter()
            .zip(r.bits.iter())
            .filter(|(a, b)| a != b)
            .count();
        let ber = errors as f64 / sent.len() as f64;
        assert!(ber < 1e-2, "ber {}", ber);
        assert!(finish_packet(&cfg, &r).is_some());
    }
}
