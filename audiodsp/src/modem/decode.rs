use std::collections::HashMap;

use crate::consts::{
    BIT_DURATION, MAX_PAYLOAD_LEN, PKT_BYTES, PKT_CHUNK, PKT_HEADER, PKT_NPARITY, PREAMBLE,
};
use crate::crc::crc32;
use crate::rs::rs_correct_msg;

use super::spectrum::FskSpectrum;

fn bit_at(spec: &mut FskSpectrum, samples: &[f32], offset: usize) -> (u8, f64, f64) {
    let (m0, m1) = spec.mags(samples, offset);
    let energy = m0 + m1;
    let confidence = if energy > 1e-9 {
        (m1 - m0).abs() / energy
    } else {
        0.0
    };
    (if m1 > m0 { 1 } else { 0 }, confidence, energy)
}

fn score_preamble_at(spec: &mut FskSpectrum, samples: &[f32], offset: usize) -> (f64, f64) {
    let bit_samples = spec.len();
    let mut score = 0f64;
    let mut min_energy = f64::INFINITY;
    for i in 0..PREAMBLE.len() {
        let start = offset + i * bit_samples;
        if start + bit_samples > samples.len() {
            return (f64::NEG_INFINITY, 0.0);
        }
        let (bit, confidence, energy) = bit_at(spec, samples, start);
        if energy < min_energy {
            min_energy = energy;
        }
        score += if bit == PREAMBLE[i] {
            confidence
        } else {
            -confidence * 1.5
        };
    }
    (score, min_energy)
}

struct Pkt {
    seq: usize,
    total: usize,
    with_crc_len: usize,
    chunk: Vec<u8>,
}

fn decode_packet_at(spec: &mut FskSpectrum, samples: &[f32], preamble_start: usize) -> Option<Pkt> {
    let bit_samples = spec.len();
    debug_assert_eq!(spec.len(), bit_samples, "FskSpectrum changed the bit window length");
    let preamble_samples = PREAMBLE.len() * bit_samples;
    let cursor = preamble_start + preamble_samples;
    let need = PKT_BYTES * 8 * bit_samples;
    if cursor + need > samples.len() {
        return None;
    }
    let mut body = vec![0u8; PKT_BYTES];
    for b in 0..PKT_BYTES {
        let mut v = 0u8;
        for i in 0..8 {
            let (bit, _, _) = bit_at(spec, samples, cursor + (b * 8 + i) * bit_samples);
            v = (v << 1) | (bit & 1);
        }
        body[b] = v;
    }
    let data = rs_correct_msg(&body, PKT_NPARITY).ok()?;
    let seq = data[0] as usize;
    let total = data[1] as usize;
    let with_crc_len = data[2] as usize;
    if total < 1 || total > 64 {
        return None;
    }
    if seq >= total {
        return None;
    }
    if with_crc_len < 5 || with_crc_len > MAX_PAYLOAD_LEN + 5 {
        return None;
    }
    Some(Pkt {
        seq,
        total,
        with_crc_len,
        chunk: data[PKT_HEADER..PKT_HEADER + PKT_CHUNK].to_vec(),
    })
}

fn refine_preamble(spec: &mut FskSpectrum, samples: &[f32], coarse: usize, radius: usize, step: usize) -> usize {
    let mut best = f64::NEG_INFINITY;
    let mut best_off = coarse;
    let mut d = -(radius as isize);
    while d <= radius as isize {
        let off = coarse as isize + d;
        if off >= 0 {
            let (score, _) = score_preamble_at(spec, samples, off as usize);
            if score > best {
                best = score;
                best_off = off as usize;
            }
        }
        d += step as isize;
    }
    best_off
}

pub struct DecodeResult {
    pub payload: Option<Vec<u8>>,
    pub have: usize,
    pub total: Option<usize>,
}

pub fn decode_recording(samples: &[f32], sample_rate: u32) -> DecodeResult {
    let bit_samples = (BIT_DURATION * sample_rate as f32).round() as usize;
    if bit_samples == 0 {
        return DecodeResult { payload: None, have: 0, total: None };
    }
    let mut spec = FskSpectrum::new(bit_samples, sample_rate);
    debug_assert_eq!(spec.len(), bit_samples, "FskSpectrum changed the bit window length");
    let search_step = (bit_samples / 6).max(1);
    let preamble_samples = PREAMBLE.len() * bit_samples;
    if samples.len() < preamble_samples {
        return DecodeResult { payload: None, have: 0, total: None };
    }
    let max_start = samples.len() - preamble_samples;
    let lock_threshold = PREAMBLE.len() as f64 * 0.35;

    let mut cand: Vec<(usize, f64)> = vec![];
    let mut offset = 0;
    while offset <= max_start {
        let (score, _) = score_preamble_at(&mut spec, samples, offset);
        if score >= lock_threshold {
            cand.push((offset, score));
        }
        offset += search_step;
    }
    cand.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let min_sep = (preamble_samples as f64 * 0.75).round() as usize;
    let mut picked: Vec<usize> = vec![];
    for (off, _) in &cand {
        let near = picked.iter().any(|&p| off.abs_diff(p) < min_sep);
        if !near {
            picked.push(*off);
        }
    }

    let mut chunks: HashMap<usize, Vec<u8>> = HashMap::new();
    let mut total: Option<usize> = None;
    let mut with_crc_len: Option<usize> = None;
    let refine_radius = search_step;
    let refine_step = (bit_samples / 40).max(1);

    for coarse in picked {
        let refined = refine_preamble(&mut spec, samples, coarse, refine_radius, refine_step);
        let pkt = match decode_packet_at(&mut spec, samples, refined) {
            Some(p) => p,
            None => continue,
        };
        if total.is_none() {
            total = Some(pkt.total);
            with_crc_len = Some(pkt.with_crc_len);
        }
        if Some(pkt.total) != total || Some(pkt.with_crc_len) != with_crc_len {
            continue;
        }
        chunks.entry(pkt.seq).or_insert(pkt.chunk);
        if chunks.len() == total.unwrap() {
            break;
        }
    }

    let total = match total {
        Some(t) => t,
        None => return DecodeResult { payload: None, have: 0, total: None },
    };
    let with_crc_len = with_crc_len.unwrap();
    if chunks.len() < total {
        return DecodeResult { payload: None, have: chunks.len(), total: Some(total) };
    }

    let mut with_crc = vec![];
    for seq in 0..total {
        match chunks.get(&seq) {
            Some(c) => with_crc.extend_from_slice(c),
            None => return DecodeResult { payload: None, have: chunks.len(), total: Some(total) },
        }
    }
    if with_crc_len > with_crc.len() {
        return DecodeResult { payload: None, have: chunks.len(), total: Some(total) };
    }
    let trimmed = &with_crc[..with_crc_len];
    let len = trimmed[0] as usize;
    if len > MAX_PAYLOAD_LEN || len + 5 != with_crc_len {
        return DecodeResult { payload: None, have: chunks.len(), total: Some(total) };
    }
    let payload = trimmed[1..1 + len].to_vec();
    let mut for_crc = vec![len as u8];
    for_crc.extend_from_slice(&payload);
    let expected = crc32(&for_crc);
    let received = ((trimmed[1 + len] as u32) << 24)
        | ((trimmed[1 + len + 1] as u32) << 16)
        | ((trimmed[1 + len + 2] as u32) << 8)
        | (trimmed[1 + len + 3] as u32);
    if expected != received {
        return DecodeResult { payload: None, have: chunks.len(), total: Some(total) };
    }
    DecodeResult { payload: Some(payload), have: total, total: Some(total) }
}

pub fn decode(samples: &[f32], sample_rate: u32) -> Option<Vec<u8>> {
    decode_recording(samples, sample_rate).payload
}
