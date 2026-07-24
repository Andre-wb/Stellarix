use super::config::{OfdmConfig, BAND_HIGH_HZ, BAND_LOW_HZ};

fn tukey(n: usize, alpha: f64) -> Vec<f32> {
    let mut w = vec![1f32; n];
    if n < 2 {
        return w;
    }
    let l = (alpha * n as f64 / 2.0).floor() as usize;
    for i in 0..l.min(n / 2) {
        let v = 0.5
            * (1.0
                + (std::f64::consts::PI * (2.0 * i as f64 / (alpha * n as f64) - 1.0)).cos());
        w[i] = v as f32;
        w[n - 1 - i] = v as f32;
    }
    w
}

pub fn chirp(cfg: &OfdmConfig) -> Vec<f32> {
    let n = cfg.chirp_len();
    let fs = cfg.fs as f64;
    let t_total = n as f64 / fs;
    let win = tukey(n, 0.1);
    (0..n)
        .map(|i| {
            let t = i as f64 / fs;
            let phase = std::f64::consts::TAU
                * (BAND_LOW_HZ * t + (BAND_HIGH_HZ - BAND_LOW_HZ) * t * t / (2.0 * t_total));
            phase.sin() as f32 * win[i]
        })
        .collect()
}

pub fn find_chirp(rx: &[f32], chirp: &[f32], threshold: f32) -> Option<usize> {
    let n = chirp.len();
    if rx.len() < n {
        return None;
    }
    let t_energy: f64 = chirp.iter().map(|&v| v as f64 * v as f64).sum();
    if t_energy < 1e-12 {
        return None;
    }
    let mut prefix = Vec::with_capacity(rx.len() + 1);
    prefix.push(0f64);
    for &v in rx {
        prefix.push(prefix.last().unwrap() + v as f64 * v as f64);
    }
    let corr = |d: usize| -> f64 {
        let e = prefix[d + n] - prefix[d];
        if e < 1e-9 {
            return 0.0;
        }
        let mut acc = 0f64;
        for i in 0..n {
            acc += rx[d + i] as f64 * chirp[i] as f64;
        }
        acc / (e * t_energy).sqrt()
    };
    let max_d = rx.len() - n;
    let step = 4usize;
    let mut d = 0usize;
    let mut coarse: Option<usize> = None;
    while d <= max_d {
        if corr(d) >= threshold as f64 {
            coarse = Some(d);
            break;
        }
        d += step;
    }
    let coarse = coarse?;
    let lo = coarse.saturating_sub(step);
    let hi = (coarse + 256).min(max_d);
    let mut best = lo;
    let mut best_c = f64::NEG_INFINITY;
    for p in lo..=hi {
        let c = corr(p);
        if c > best_c {
            best_c = c;
            best = p;
        }
    }
    Some(best)
}

pub fn refine_by_cp(rx: &[f32], approx: usize, cfg: &OfdmConfig) -> (usize, f32) {
    let n = cfg.n_fft;
    let cp = cfg.cp_len;
    let radius = 200usize;
    let lo = approx.saturating_sub(radius);
    let hi = approx + radius;
    let mut best = approx;
    let mut best_m = f64::NEG_INFINITY;
    let mut best_p = 0f64;
    for d in lo..=hi {
        if d + cp + n > rx.len() {
            break;
        }
        let mut p = 0f64;
        let mut e = 0f64;
        for i in 0..cp {
            p += rx[d + i] as f64 * rx[d + i + n] as f64;
            e += (rx[d + i + n] as f64) * (rx[d + i + n] as f64);
        }
        if e < 1e-12 {
            continue;
        }
        let m = p * p / (e * e);
        if m > best_m {
            best_m = m;
            best = d;
            best_p = p;
        }
    }
    let cfo = if best_p < 0.0 { 0.5 } else { 0.0 };
    (best, cfo)
}

pub struct SfoTracker {
    sym_len: f64,
    n_fft: f64,
    cp_len: f64,
    sxy: f64,
    sxx: f64,
}

impl SfoTracker {
    pub fn new(cfg: &OfdmConfig) -> Self {
        SfoTracker {
            sym_len: cfg.symbol_samples() as f64,
            n_fft: cfg.n_fft as f64,
            cp_len: cfg.cp_len as f64,
            sxy: 0.0,
            sxx: 0.0,
        }
    }

    pub(crate) fn slope_to_delta(&self, timing_slope: f32) -> f64 {
        -(timing_slope as f64) * self.n_fft / std::f64::consts::TAU
    }

    pub(crate) fn record(&mut self, symbol_index: usize, delta_total: f64) {
        if delta_total.abs() > self.cp_len {
            return;
        }
        let x = symbol_index as f64 * self.sym_len;
        self.sxy += x * delta_total;
        self.sxx += x * x;
    }

    pub fn update(&mut self, symbol_index: usize, timing_slope: f32) {
        let delta = self.slope_to_delta(timing_slope);
        self.record(symbol_index, delta);
    }

    pub fn estimate(&self) -> f64 {
        if self.sxx == 0.0 {
            return 0.0;
        }
        (self.sxy / self.sxx).clamp(-0.005, 0.005)
    }

    pub fn position(&self, start: usize, n: usize) -> usize {
        let pos = start as f64 + n as f64 * self.sym_len * (1.0 + self.estimate());
        pos.round().max(0.0) as usize
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ofdm::config::OfdmConfig;
    use crate::ofdm::util::Prng;

    #[test]
    fn finds_chirp_at_known_offset() {
        let cfg = OfdmConfig::default_48k();
        let c = chirp(&cfg);
        let mut rng = Prng::new(7);
        for &offset in &[0usize, 1234, 20000] {
            let mut rx = vec![0f32; offset + c.len() + 4000];
            for v in rx.iter_mut() {
                *v = (rng.next_f32() - 0.5) * 0.02;
            }
            for (i, &s) in c.iter().enumerate() {
                rx[offset + i] += s * 0.5;
            }
            let found = find_chirp(&rx, &c, 0.35).expect("chirp not found");
            assert!(
                found.abs_diff(offset) <= 5,
                "offset {} found {}",
                offset,
                found
            );
        }
    }
}
