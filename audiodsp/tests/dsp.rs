use audiodsp::{decode, encode_payload};

fn rng(seed: u32) -> impl FnMut() -> u32 {
    let mut a = seed;
    move || {
        a ^= a << 13;
        a ^= a >> 17;
        a ^= a << 5;
        a
    }
}

fn rand_bytes(r: &mut impl FnMut() -> u32, n: usize) -> Vec<u8> {
    (0..n).map(|_| (r() & 0xff) as u8).collect()
}

fn resample(src: &[f32], drift: f64, start_pad: usize, r: &mut impl FnMut() -> u32, noise: f32) -> Vec<f32> {
    let body_len = (src.len() as f64 / (1.0 + drift)).floor() as usize;
    let mut out = vec![0f32; start_pad + body_len + 8000];
    for i in 0..body_len {
        let s = i as f64 * (1.0 + drift);
        let i0 = s.floor() as usize;
        let frac = (s - i0 as f64) as f32;
        let a = *src.get(i0).unwrap_or(&0.0);
        let b = *src.get(i0 + 1).unwrap_or(&0.0);
        out[start_pad + i] = a + (b - a) * frac;
    }
    if noise > 0.0 {
        for v in out.iter_mut() {
            *v += ((r() as f32 / u32::MAX as f32) * 2.0 - 1.0) * noise;
        }
    }
    out
}

#[test]
fn roundtrip_clean() {
    let mut r = rng(10);
    for &rate in &[44100u32, 48000u32] {
        for n in [1usize, 4, 8] {
            let key = rand_bytes(&mut r, n);
            let samples = encode_payload(&key, rate, 0.6);
            let got = decode(&samples, rate);
            assert_eq!(got.as_deref(), Some(&key[..]), "rate={} n={}", rate, n);
        }
    }
}

#[test]
fn cross_rate_encode48_decode44() {
    let mut r = rng(20);
    for _ in 0..4 {
        let key = rand_bytes(&mut r, 4);
        let tx = encode_payload(&key, 48000, 0.6);
        let rx = resample(&tx, 48000.0 / 44100.0 - 1.0, 3000, &mut r, 0.02);
        let got = decode(&rx, 44100);
        assert_eq!(got.as_deref(), Some(&key[..]), "cross-rate decode failed");
    }
}

#[test]
fn drift_noise_matrix() {
    let mut r = rng(99);
    let drifts = [0.0f64, 0.0002, 0.0005, 0.001, 0.002, 0.005];
    let noises = [0.0f32, 0.05];
    let mut wrong = 0;
    let mut report = String::new();
    let mut real_ok = true;
    for &d in &drifts {
        let mut ex = 0;
        let mut tot = 0;
        for &noise in &noises {
            for _ in 0..3 {
                let key = rand_bytes(&mut r, 4);
                let tx = encode_payload(&key, 44100, 0.6);
                let rx = resample(&tx, d, 2000 + (r() as usize % 6000), &mut r, noise);
                tot += 1;
                match decode(&rx, 44100) {
                    Some(p) if p == key => ex += 1,
                    Some(_) => wrong += 1,
                    None => {}
                }
            }
        }
        report.push_str(&format!("  drift={:+.3}% exact={}/{}\n", d * 100.0, ex, tot));
        if d.abs() <= 0.0005 && ex != tot {
            real_ok = false;
        }
    }
    eprintln!("drift tolerance curve (44100 Hz):\n{}", report);
    assert_eq!(wrong, 0, "silently wrong under drift/noise\n{}", report);
    assert!(real_ok, "exact-decode not 100% within realistic drift (<=0.05%)\n{}", report);
}

#[test]
fn heavy_corruption_never_silently_wrong() {
    let mut r = rng(2);
    let mut silent = 0;
    for _ in 0..30 {
        let key = rand_bytes(&mut r, 4);
        let mut samples = encode_payload(&key, 44100, 0.6);
        let ncorrupt = samples.len() / 3;
        for _ in 0..ncorrupt {
            let i = r() as usize % samples.len();
            samples[i] += ((r() as f32 / u32::MAX as f32) * 2.0 - 1.0) * 0.6;
        }
        if let Some(p) = decode(&samples, 44100) {
            if p != key {
                silent += 1;
            }
        }
    }
    assert_eq!(silent, 0, "frame decode silently wrong");
}

#[test]
fn packet_loss_never_silently_wrong() {
    let mut r = rng(7);
    let mut silent = 0;
    for _ in 0..20 {
        let key = rand_bytes(&mut r, 8);
        let mut samples = encode_payload(&key, 44100, 0.6);
        let seg = samples.len() / 5;
        let start = seg + (r() as usize % seg);
        for i in start..(start + seg).min(samples.len()) {
            samples[i] = ((r() as f32 / u32::MAX as f32) * 2.0 - 1.0) * 0.5;
        }
        if let Some(p) = decode(&samples, 44100) {
            if p != key {
                silent += 1;
            }
        }
    }
    assert_eq!(silent, 0, "packet loss produced silently-wrong decode");
}
