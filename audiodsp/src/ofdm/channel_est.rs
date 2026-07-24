use realfft::num_complex::Complex;

use super::config::OfdmConfig;

pub struct ChannelEstimate {
    pub h: Vec<Complex<f32>>,
    pub snr_db: Vec<f32>,
    pub noise_power: f32,
    pub mean_snr_db: f32,
}

pub(crate) fn noise_from_spectrum(cfg: &OfdmConfig, spectrum: &[Complex<f32>]) -> f32 {
    let half = cfg.n_fft / 2;
    let mut bins: Vec<usize> = vec![];
    if cfg.k_min > 30 {
        bins.extend(20..cfg.k_min - 10);
    }
    if cfg.k_max + 10 < half - 20 {
        bins.extend(cfg.k_max + 10..half - 20);
    }
    if bins.is_empty() {
        bins.extend(1..cfg.k_min.max(2));
    }
    let s: f64 = bins.iter().map(|&k| spectrum[k].norm_sqr() as f64).sum();
    ((s / bins.len() as f64) as f32).max(1e-20)
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
    let mut h = Vec::with_capacity(nsub);
    for i in 0..nsub {
        let prev = raw[if i == 0 { 0 } else { i - 1 }];
        let next = raw[(i + 1).min(nsub - 1)];
        h.push((prev + raw[i] * 2.0 + next) * 0.25);
    }
    let noise_power = noise_from_spectrum(cfg, spectrum);
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
