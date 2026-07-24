use std::sync::OnceLock;

use realfft::num_complex::Complex;

use super::config::Modulation;

static BPSK: OnceLock<Vec<Complex<f32>>> = OnceLock::new();
static QPSK: OnceLock<Vec<Complex<f32>>> = OnceLock::new();
static QAM16: OnceLock<Vec<Complex<f32>>> = OnceLock::new();
static QAM64: OnceLock<Vec<Complex<f32>>> = OnceLock::new();

pub(crate) fn table(m: Modulation) -> &'static [Complex<f32>] {
    match m {
        Modulation::Bpsk => BPSK.get_or_init(build_bpsk),
        Modulation::Qpsk => QPSK.get_or_init(build_qpsk),
        Modulation::Qam16 => QAM16.get_or_init(|| build_qam(2, 10.0)),
        Modulation::Qam64 => QAM64.get_or_init(|| build_qam(3, 42.0)),
    }
}

fn build_bpsk() -> Vec<Complex<f32>> {
    vec![Complex::new(1.0, 0.0), Complex::new(-1.0, 0.0)]
}

fn build_qpsk() -> Vec<Complex<f32>> {
    let s = std::f32::consts::FRAC_1_SQRT_2;
    (0..4u32)
        .map(|v| {
            let b1 = ((v >> 1) & 1) as i32;
            let b0 = (v & 1) as i32;
            Complex::new(s * (1 - 2 * b0) as f32, s * (1 - 2 * b1) as f32)
        })
        .collect()
}

fn gray_level(bits: u32, width: usize) -> f32 {
    let mut i = bits;
    let mut mask = i >> 1;
    while mask != 0 {
        i ^= mask;
        mask >>= 1;
    }
    (2 * i) as f32 - ((1u32 << width) - 1) as f32
}

fn build_qam(axis_bits: usize, norm_power: f32) -> Vec<Complex<f32>> {
    let s = 1.0 / norm_power.sqrt();
    let count = 1u32 << (2 * axis_bits);
    (0..count)
        .map(|v| {
            let hi = v >> axis_bits;
            let lo = v & ((1 << axis_bits) - 1);
            Complex::new(
                s * gray_level(hi, axis_bits),
                s * gray_level(lo, axis_bits),
            )
        })
        .collect()
}

pub(crate) fn map_bits(m: Modulation, bits: &[u8]) -> Complex<f32> {
    let mut idx = 0usize;
    for &b in bits {
        idx = (idx << 1) | (b & 1) as usize;
    }
    table(m)[idx]
}

pub(crate) fn demap(m: Modulation, x: Complex<f32>) -> (usize, f32) {
    let t = table(m);
    let mut best = 0usize;
    let mut best_d = f32::INFINITY;
    for (i, p) in t.iter().enumerate() {
        let d = (x - p).norm_sqr();
        if d < best_d {
            best_d = d;
            best = i;
        }
    }
    (best, best_d.sqrt())
}

pub(crate) fn push_index_bits(idx: usize, width: usize, out: &mut Vec<u8>) {
    for i in (0..width).rev() {
        out.push(((idx >> i) & 1) as u8);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALL: [Modulation; 4] = [
        Modulation::Bpsk,
        Modulation::Qpsk,
        Modulation::Qam16,
        Modulation::Qam64,
    ];

    #[test]
    fn map_demap_roundtrip() {
        for m in ALL {
            let bpc = m.bits_per_carrier();
            for idx in 0..(1usize << bpc) {
                let mut bits = vec![];
                push_index_bits(idx, bpc, &mut bits);
                let p = map_bits(m, &bits);
                let (got, dist) = demap(m, p);
                assert_eq!(got, idx);
                assert!(dist < 1e-6);
            }
        }
    }

    #[test]
    fn unit_average_power() {
        for m in ALL {
            let t = table(m);
            let p: f32 = t.iter().map(|c| c.norm_sqr()).sum::<f32>() / t.len() as f32;
            assert!((p - 1.0).abs() < 0.01, "{:?} power {}", m, p);
        }
    }

    #[test]
    fn gray_neighbours_differ_by_one_bit() {
        for m in ALL {
            let t = table(m);
            let mut dmin = f32::INFINITY;
            for i in 0..t.len() {
                for j in 0..i {
                    dmin = dmin.min((t[i] - t[j]).norm());
                }
            }
            if t.len() == 2 {
                continue;
            }
            for i in 0..t.len() {
                for j in 0..i {
                    if ((t[i] - t[j]).norm() - dmin).abs() < 1e-4 {
                        assert_eq!((i ^ j).count_ones(), 1, "{:?} {} {}", m, i, j);
                    }
                }
            }
        }
    }

    #[test]
    fn spec_reference_points() {
        let s2 = std::f32::consts::FRAC_1_SQRT_2;
        let q = table(Modulation::Qpsk);
        assert!((q[0b00] - Complex::new(s2, s2)).norm() < 1e-6);
        assert!((q[0b01] - Complex::new(-s2, s2)).norm() < 1e-6);
        assert!((q[0b11] - Complex::new(-s2, -s2)).norm() < 1e-6);
        assert!((q[0b10] - Complex::new(s2, -s2)).norm() < 1e-6);
        let s10 = 1.0 / 10f32.sqrt();
        let t = table(Modulation::Qam16);
        assert!((t[0b0000] - Complex::new(-3.0 * s10, -3.0 * s10)).norm() < 1e-6);
        assert!((t[0b1000] - Complex::new(3.0 * s10, -3.0 * s10)).norm() < 1e-6);
        assert!((t[0b1110] - Complex::new(s10, 3.0 * s10)).norm() < 1e-6);
    }
}
