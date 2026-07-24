use audiodsp::ofdm::{
    chirp, decode_transmission, decode_transmission_encrypted, encode_transmission,
    encode_transmission_encrypted, find_chirp, max_packet_payload, Demodulator,
    Modulation, Modulator, OfdmConfig, CHIRP_THRESHOLD,
};

fn rng(seed: u64) -> impl FnMut() -> u64 {
    let mut s = seed;
    move || {
        s = s.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = s;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
}

fn rand_bytes(r: &mut impl FnMut() -> u64, n: usize) -> Vec<u8> {
    (0..n).map(|_| (r() & 0xff) as u8).collect()
}

fn add_awgn(rx: &mut [f32], r: &mut impl FnMut() -> u64, sigma: f32) {
    for v in rx.iter_mut() {
        let u = (r() >> 40) as f32 / (1u64 << 24) as f32;
        *v += (u * 2.0 - 1.0) * sigma * 1.732;
    }
}

fn active_rms(x: &[f32]) -> f32 {
    let mut acc = 0f64;
    let mut n = 0usize;
    for &v in x {
        if v.abs() > 0.0 {
            acc += v as f64 * v as f64;
            n += 1;
        }
    }
    ((acc / n.max(1) as f64).sqrt()) as f32
}

fn resample(src: &[f32], drift: f64, pad: usize) -> Vec<f32> {
    let body = (src.len() as f64 / (1.0 + drift)).floor() as usize;
    let mut out = vec![0f32; pad + body + 8000];
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

fn echo(src: &[f32], taps: &[(usize, f32)]) -> Vec<f32> {
    let max_d = taps.iter().map(|t| t.0).max().unwrap_or(0);
    let mut out = vec![0f32; src.len() + max_d];
    for &(d, g) in taps {
        for (i, &v) in src.iter().enumerate() {
            out[i + d] += v * g;
        }
    }
    out
}

#[test]
fn roundtrip_clean_all_modulations() {
    let mut r = rng(1);
    for m in [
        Modulation::Bpsk,
        Modulation::Qpsk,
        Modulation::Qam16,
        Modulation::Qam64,
    ] {
        let mut cfg = OfdmConfig::default_48k();
        cfg.modulation = m;
        let payload = rand_bytes(&mut r, 96);
        let tx = encode_transmission(&payload, &cfg);
        let got = decode_transmission(&tx, &cfg);
        assert_eq!(got.as_deref(), Some(&payload[..]), "{:?}", m);
    }
}

#[test]
fn roundtrip_44100() {
    let mut r = rng(2);
    let cfg = OfdmConfig::for_sample_rate(44100);
    cfg.validate().unwrap();
    let payload = rand_bytes(&mut r, 64);
    let tx = encode_transmission(&payload, &cfg);
    assert_eq!(
        decode_transmission(&tx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn delay_up_to_50k_samples() {
    let mut r = rng(3);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 48);
    let tx = encode_transmission(&payload, &cfg);
    for &delay in &[0usize, 777, 50000] {
        let mut rx = vec![0f32; delay];
        rx.extend_from_slice(&tx);
        add_awgn(&mut rx, &mut r, active_rms(&tx) * 0.01);
        assert_eq!(
            decode_transmission(&rx, &cfg).as_deref(),
            Some(&payload[..]),
            "delay {}",
            delay
        );
    }
}

#[test]
fn awgn_qpsk_decodes_at_low_snr() {
    let mut r = rng(4);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 200);
    let tx = encode_transmission(&payload, &cfg);
    let rms = active_rms(&tx);
    for &snr_db in &[20.0f32, 10.0, 6.0] {
        let sigma = rms / 10f32.powf(snr_db / 20.0);
        let mut rx = tx.clone();
        add_awgn(&mut rx, &mut r, sigma);
        assert_eq!(
            decode_transmission(&rx, &cfg).as_deref(),
            Some(&payload[..]),
            "snr {}",
            snr_db
        );
    }
}

#[test]
fn awgn_qam16_decodes_at_good_snr() {
    let mut r = rng(5);
    let mut cfg = OfdmConfig::default_48k();
    cfg.modulation = Modulation::Qam16;
    let payload = rand_bytes(&mut r, 400);
    let tx = encode_transmission(&payload, &cfg);
    let sigma = active_rms(&tx) / 10f32.powf(18.0 / 20.0);
    let mut rx = tx.clone();
    add_awgn(&mut rx, &mut r, sigma);
    assert_eq!(
        decode_transmission(&rx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn echo_within_cp() {
    let mut r = rng(6);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 128);
    let tx = encode_transmission(&payload, &cfg);
    let taps = [(0usize, 1.0f32), (288, 0.5), (720, 0.3)];
    let mut rx = echo(&tx, &taps);
    add_awgn(&mut rx, &mut r, active_rms(&tx) * 0.02);
    assert_eq!(
        decode_transmission(&rx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn sfo_100_and_500_ppm() {
    let mut r = rng(7);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 2000);
    let tx = encode_transmission(&payload, &cfg);
    for &drift in &[1e-4f64, -1e-4, 5e-4] {
        let mut rx = resample(&tx, drift, 3000);
        add_awgn(&mut rx, &mut r, active_rms(&tx) * 0.02);
        assert_eq!(
            decode_transmission(&rx, &cfg).as_deref(),
            Some(&payload[..]),
            "drift {}",
            drift
        );
    }
}

#[test]
fn sfo_2000_ppm_limit() {
    let mut r = rng(8);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 800);
    let tx = encode_transmission(&payload, &cfg);
    let rx = resample(&tx, 2e-3, 2000);
    assert_eq!(
        decode_transmission(&rx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn multi_packet_payload() {
    let mut r = rng(9);
    let cfg = OfdmConfig::default_48k();
    let single = max_packet_payload(&cfg);
    let payload = rand_bytes(&mut r, single * 2 + 500);
    let tx = encode_transmission(&payload, &cfg);
    assert_eq!(
        decode_transmission(&tx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn compressible_payload_shrinks_airtime() {
    let cfg = OfdmConfig::default_48k();
    let payload = vec![9u8; 4000];
    let tx = encode_transmission(&payload, &cfg);
    assert!(tx.len() < 70000, "tx len {}", tx.len());
    assert_eq!(
        decode_transmission(&tx, &cfg).as_deref(),
        Some(&payload[..])
    );
}

#[test]
fn encrypted_roundtrip_over_air() {
    let mut r = rng(11);
    let cfg = OfdmConfig::default_48k();
    let payload = rand_bytes(&mut r, 64);
    let key = [7u8; 32];
    let tx = encode_transmission_encrypted(&payload, &cfg, &key);
    assert_eq!(
        decode_transmission_encrypted(&tx, &cfg, &key).as_deref(),
        Some(&payload[..])
    );
    assert!(decode_transmission_encrypted(&tx, &cfg, &[8u8; 32]).is_none());
    assert!(decode_transmission(&tx, &cfg).is_none());
}

#[test]
fn channel_estimate_flat_for_ideal_channel() {
    let cfg = OfdmConfig::default_48k();
    let mut modulator = Modulator::new(cfg.clone());
    let mut demod = Demodulator::new(cfg.clone());
    let sym = modulator.training_symbol();
    let ch = demod.estimate_channel(&sym);
    let mags: Vec<f32> = ch.h.iter().map(|c| c.norm()).collect();
    let mean: f32 = mags.iter().sum::<f32>() / mags.len() as f32;
    for (i, &m) in mags.iter().enumerate() {
        assert!(
            (m - mean).abs() / mean < 0.05,
            "carrier {} mag {} mean {}",
            i,
            m,
            mean
        );
    }
    assert!(ch.mean_snr_db > 40.0);
}

#[test]
fn chirp_detection_survives_heavy_noise() {
    let mut r = rng(10);
    let cfg = OfdmConfig::default_48k();
    let c = chirp(&cfg);
    let mut rx = vec![0f32; 9000 + c.len() + 4000];
    add_awgn(&mut rx, &mut r, 0.35);
    for (i, &s) in c.iter().enumerate() {
        rx[9000 + i] += s * 0.5;
    }
    let found = find_chirp(&rx, &c, CHIRP_THRESHOLD);
    assert!(found.is_some());
    assert!(found.unwrap().abs_diff(9000) <= 5, "found {:?}", found);
}
