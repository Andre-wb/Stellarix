use crate::consts::{
    BIT_DURATION, FREQ0, FREQ1, GAP_SECONDS, MAX_PAYLOAD_LEN, PKT_BYTES, PREAMBLE, SILENCE_AFTER,
    SILENCE_BEFORE,
};
use crate::packet::{build_packets, packet_to_bits};

pub fn max_total_seconds() -> f32 {
    let dummy = vec![0u8; MAX_PAYLOAD_LEN];
    let packets = build_packets(&dummy);
    let per_packet = (PREAMBLE.len() + PKT_BYTES * 8) as f32 * BIT_DURATION + GAP_SECONDS;
    SILENCE_BEFORE + packets.len() as f32 * per_packet + SILENCE_AFTER
}

pub fn encode_payload(payload: &[u8], sample_rate: u32, gain: f32) -> Vec<f32> {
    let rate = sample_rate as f64;
    let bit_samples = (BIT_DURATION as f64 * rate).round() as usize;
    let gap_samples = (GAP_SECONDS as f64 * rate).round() as usize;
    let before = (SILENCE_BEFORE as f64 * rate).round() as usize;
    let after = (SILENCE_AFTER as f64 * rate).round() as usize;
    let ramp = (0.01 * rate).round() as usize;
    let packets = build_packets(payload);
    let mut out = vec![0f32; before];
    for body in &packets {
        let bits = packet_to_bits(body);
        let n = bits.len() * bit_samples;
        let start = out.len();
        out.resize(start + n, 0.0);
        let mut phase: f64 = 0.0;
        for (b, &bit) in bits.iter().enumerate() {
            let freq = if bit == 1 { FREQ1 } else { FREQ0 } as f64;
            let dp = 2.0 * std::f64::consts::PI * freq / rate;
            for i in 0..bit_samples {
                out[start + b * bit_samples + i] = (gain as f64 * phase.sin()) as f32;
                phase += dp;
            }
        }
        let r = ramp.min(n / 2);
        for i in 0..r {
            let f = i as f32 / ramp as f32;
            out[start + i] *= f;
            out[start + n - 1 - i] *= f;
        }
        out.extend(std::iter::repeat(0.0).take(gap_samples));
    }
    out.extend(std::iter::repeat(0.0).take(after));
    out
}
