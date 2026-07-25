use realfft::num_complex::Complex;

use super::config::OfdmConfig;

pub struct ChannelEstimate {
    pub h: Vec<Complex<f32>>,
    pub snr_db: Vec<f32>,
    pub noise_power: f32,
    pub mean_snr_db: f32,
}

fn noise_from_residual(raw: &[Complex<f32>], h: &[Complex<f32>]) -> f32 {
    let n = raw.len();
    if n < 8 {
        let s: f64 = raw
            .iter()
            .zip(h)
            .map(|(a, b)| (a - b).norm_sqr() as f64)
            .sum();
        return (((s / n as f64) * 16.0 / 6.0) as f32).max(1e-20);
    }
    let mut res: Vec<f32> = (1..n - 1).map(|i| (raw[i] - h[i]).norm_sqr()).collect();
    let mid = res.len() / 2;
    res.select_nth_unstable_by(mid, |a, b| a.partial_cmp(b).unwrap());
    let med = res[mid] as f64;
    ((med * 16.0 / (6.0 * std::f64::consts::LN_2)) as f32).max(1e-20)
}

fn carrier_phase_slope(raw: &[Complex<f32>]) -> f32 {
    if raw.len() < 2 {
        return 0.0;
    }
    let step: Complex<f32> = raw.windows(2).map(|w| w[1] * w[0].conj()).sum();
    step.arg()
}

pub(crate) fn estimate(
    cfg: &OfdmConfig,
    spectrum: &[Complex<f32>],
    training: &[Complex<f32>],
) -> ChannelEstimate {
    let nsub = cfg.n_subcarriers();
    let mut raw = Vec::with_capacity(nsub);
    for i in 0..nsub {
        raw.push(spectrum[cfg.k_min + i] * training[i].conj());
    }
    let slope = carrier_phase_slope(&raw);
    let mut h = Vec::with_capacity(nsub);
    for i in 0..nsub {
        let p = if i == 0 { 0 } else { i - 1 };
        let q = (i + 1).min(nsub - 1);
        let wp = Complex::from_polar(1.0, slope * (i as isize - p as isize) as f32);
        let wq = Complex::from_polar(1.0, slope * (i as isize - q as isize) as f32);
        h.push((raw[p] * wp + raw[i] * 2.0 + raw[q] * wq) * 0.25);
    }
    let noise_power = noise_from_residual(&raw, &h);
    let snr_db: Vec<f32> = h
        .iter()
        .map(|c| 10.0 * (c.norm_sqr() / noise_power).max(1e-12).log10())
        .collect();
    let mean_pow =
        (h.iter().map(|c| c.norm_sqr() as f64).sum::<f64>() / nsub as f64) as f32;
    let mean_snr_db = 10.0 * (mean_pow / noise_power).max(1e-12).log10();
    ChannelEstimate {
        h,
        snr_db,
        noise_power,
        mean_snr_db,
    }
}
