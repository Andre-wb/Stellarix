use realfft::num_complex::Complex;

use super::config::OfdmConfig;
use super::util::Prng;

fn unit_qpsk_seq(seed: u64, n: usize) -> Vec<Complex<f32>> {
    let mut rng = Prng::new(seed);
    (0..n)
        .map(|_| {
            let q = (rng.next_u64() & 3) as f32;
            let a = std::f32::consts::FRAC_PI_4 + q * std::f32::consts::FRAC_PI_2;
            Complex::new(a.cos(), a.sin())
        })
        .collect()
}

pub(crate) fn training_values(cfg: &OfdmConfig) -> Vec<Complex<f32>> {
    unit_qpsk_seq(cfg.phase_seed ^ 0x5452_4149_4E49_4E47, cfg.n_subcarriers())
}

pub(crate) fn pilot_values(cfg: &OfdmConfig) -> Vec<Complex<f32>> {
    unit_qpsk_seq(cfg.phase_seed ^ 0x0050_494C_4F54_5321, cfg.n_pilots())
}

pub(crate) fn phase_randomizer(cfg: &OfdmConfig) -> Vec<Complex<f32>> {
    let mut rng = Prng::new(cfg.phase_seed);
    (0..cfg.n_subcarriers())
        .map(|_| {
            let a = rng.next_f32() * std::f32::consts::TAU;
            Complex::new(a.cos(), a.sin())
        })
        .collect()
}

pub(crate) struct PilotFit {
    pub(crate) slope: f32,
    pub(crate) cpe: f32,
}

fn fit_line(points: &[(f64, f64)]) -> Option<(f64, f64)> {
    let n = points.len() as f64;
    if points.len() < 2 {
        return None;
    }
    let sx: f64 = points.iter().map(|p| p.0).sum();
    let sy: f64 = points.iter().map(|p| p.1).sum();
    let sxx: f64 = points.iter().map(|p| p.0 * p.0).sum();
    let sxy: f64 = points.iter().map(|p| p.0 * p.1).sum();
    let denom = n * sxx - sx * sx;
    if denom.abs() < 1e-12 {
        return None;
    }
    let a = (n * sxy - sx * sy) / denom;
    let b = (sy - a * sx) / n;
    Some((a, b))
}

pub(crate) fn correct_by_pilots(
    eq: &mut [Complex<f32>],
    cfg: &OfdmConfig,
    pilots: &[Complex<f32>],
    snr_db: &[f32],
) -> PilotFit {
    let stride = cfg.pilot_stride;
    let mut raw: Vec<(usize, f32)> = vec![];
    let mut pilot_i = 0usize;
    for i in (0..eq.len()).step_by(stride) {
        let phase = (eq[i] * pilots[pilot_i].conj()).arg();
        if snr_db[i] > 0.0 {
            raw.push((cfg.k_min + i, phase));
        }
        pilot_i += 1;
    }
    if raw.len() < 4 {
        raw.clear();
        pilot_i = 0;
        for i in (0..eq.len()).step_by(stride) {
            raw.push((cfg.k_min + i, (eq[i] * pilots[pilot_i].conj()).arg()));
            pilot_i += 1;
        }
    }
    let mut points: Vec<(f64, f64)> = vec![];
    let mut prev = 0f64;
    for (idx, &(k, ph)) in raw.iter().enumerate() {
        let mut p = ph as f64;
        if idx > 0 {
            while p - prev > std::f64::consts::PI {
                p -= std::f64::consts::TAU;
            }
            while prev - p > std::f64::consts::PI {
                p += std::f64::consts::TAU;
            }
        }
        prev = p;
        points.push((k as f64, p));
    }
    let mut fit = match fit_line(&points) {
        Some(f) => f,
        None => return PilotFit { slope: 0.0, cpe: 0.0 },
    };
    let kept: Vec<(f64, f64)> = points
        .iter()
        .copied()
        .filter(|&(x, y)| (y - (fit.0 * x + fit.1)).abs() <= 1.0)
        .collect();
    if kept.len() >= 4 && kept.len() < points.len() {
        if let Some(f) = fit_line(&kept) {
            fit = f;
        }
    }
    let (a, b) = fit;
    for (i, v) in eq.iter_mut().enumerate() {
        let phase = a * (cfg.k_min + i) as f64 + b;
        *v *= Complex::from_polar(1.0, -phase as f32);
    }
    PilotFit {
        slope: a as f32,
        cpe: b as f32,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ofdm::config::OfdmConfig;

    #[test]
    fn pilot_fit_removes_phase_ramp() {
        let cfg = OfdmConfig::default_48k();
        let pilots = pilot_values(&cfg);
        let nsub = cfg.n_subcarriers();
        let a = 0.003f32;
        let b = 0.4f32;
        let mut eq: Vec<Complex<f32>> = vec![];
        let mut pilot_i = 0;
        for i in 0..nsub {
            let base = if i % cfg.pilot_stride == 0 {
                pilot_i += 1;
                pilots[pilot_i - 1]
            } else {
                Complex::new(std::f32::consts::FRAC_1_SQRT_2, std::f32::consts::FRAC_1_SQRT_2)
            };
            let phase = a * (cfg.k_min + i) as f32 + b;
            eq.push(base * Complex::from_polar(1.0, phase));
        }
        let snr = vec![30f32; nsub];
        let fit = correct_by_pilots(&mut eq, &cfg, &pilots, &snr);
        assert!((fit.slope - a).abs() < 1e-4, "slope {}", fit.slope);
        for i in 0..nsub {
            if i % cfg.pilot_stride != 0 {
                let d = (eq[i]
                    - Complex::new(
                        std::f32::consts::FRAC_1_SQRT_2,
                        std::f32::consts::FRAC_1_SQRT_2,
                    ))
                .norm();
                assert!(d < 1e-3, "carrier {} off by {}", i, d);
            }
        }
    }
}
