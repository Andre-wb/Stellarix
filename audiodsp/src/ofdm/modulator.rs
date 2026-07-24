use std::sync::Arc;

use realfft::num_complex::Complex;
use realfft::{ComplexToReal, RealFftPlanner};

use super::config::{Modulation, OfdmConfig};
use super::constellation;
use super::framing::{header_bits, PacketHeader};
use super::pilots::{phase_randomizer, pilot_values, training_values};
use super::sync::chirp;

pub struct Modulator {
    cfg: OfdmConfig,
    ifft: Arc<dyn ComplexToReal<f32>>,
    spec: Vec<Complex<f32>>,
    time: Vec<f32>,
    scratch: Vec<Complex<f32>>,
    randomizer: Vec<Complex<f32>>,
    training: Vec<Complex<f32>>,
    pilots: Vec<Complex<f32>>,
}

impl Modulator {
    pub fn new(cfg: OfdmConfig) -> Self {
        let mut planner = RealFftPlanner::<f32>::new();
        let ifft = planner.plan_fft_inverse(cfg.n_fft);
        let spec = ifft.make_input_vec();
        let time = ifft.make_output_vec();
        let scratch = ifft.make_scratch_vec();
        let randomizer = phase_randomizer(&cfg);
        let training = training_values(&cfg);
        let pilots = pilot_values(&cfg);
        Modulator {
            cfg,
            ifft,
            spec,
            time,
            scratch,
            randomizer,
            training,
            pilots,
        }
    }

    pub fn config(&self) -> &OfdmConfig {
        &self.cfg
    }

    fn synth(&mut self, band: &[Complex<f32>], randomize: bool) -> Vec<f32> {
        for v in self.spec.iter_mut() {
            *v = Complex::new(0.0, 0.0);
        }
        for (i, &val) in band.iter().enumerate() {
            let x = if randomize { val * self.randomizer[i] } else { val };
            self.spec[self.cfg.k_min + i] = x;
        }
        self.ifft
            .process_with_scratch(&mut self.spec, &mut self.time, &mut self.scratch)
            .expect("planned fft sizes");
        let cp = self.cfg.cp_len;
        let n = self.cfg.n_fft;
        let mut out = Vec::with_capacity(cp + n);
        out.extend_from_slice(&self.time[n - cp..]);
        out.extend_from_slice(&self.time);
        out
    }

    fn band_for_bits(&self, bits: &[u8], modulation: Modulation) -> Vec<Complex<f32>> {
        let bpc = modulation.bits_per_carrier();
        let nsub = self.cfg.n_subcarriers();
        let mut band = Vec::with_capacity(nsub);
        let mut pilot_i = 0usize;
        let mut cursor = 0usize;
        let mut chunk = [0u8; 8];
        for i in 0..nsub {
            if i % self.cfg.pilot_stride == 0 {
                band.push(self.pilots[pilot_i]);
                pilot_i += 1;
            } else {
                chunk[..bpc].fill(0);
                let take = bits.len().saturating_sub(cursor).min(bpc);
                if take > 0 {
                    chunk[..take].copy_from_slice(&bits[cursor..cursor + take]);
                }
                band.push(constellation::map_bits(modulation, &chunk[..bpc]));
                cursor += bpc;
            }
        }
        band
    }

    pub fn training_symbol(&mut self) -> Vec<f32> {
        let band = self.training.clone();
        self.synth(&band, false)
    }

    pub fn header_symbol(&mut self, hdr: &PacketHeader) -> Vec<f32> {
        let hb = header_bits(hdr);
        let nd = self.cfg.n_data_carriers();
        let bits: Vec<u8> = (0..nd).map(|i| hb[i % hb.len()]).collect();
        let band = self.band_for_bits(&bits, Modulation::Bpsk);
        self.synth(&band, true)
    }

    pub fn data_symbol(&mut self, bits: &[u8]) -> Vec<f32> {
        let band = self.band_for_bits(bits, self.cfg.modulation);
        self.synth(&band, true)
    }

    pub fn build_packet(&mut self, hdr: &PacketHeader, payload_bits: &[u8]) -> Vec<f32> {
        let saved = self.cfg.modulation;
        self.cfg.modulation = hdr.modulation;
        let bps = self.cfg.bits_per_symbol();
        let mut body = self.training_symbol();
        body.extend(self.header_symbol(hdr));
        for s in 0..hdr.n_data_symbols as usize {
            let lo = (s * bps).min(payload_bits.len());
            let hi = ((s + 1) * bps).min(payload_bits.len());
            body.extend(self.data_symbol(&payload_bits[lo..hi]));
        }
        self.cfg.modulation = saved;
        let acc: f64 = body.iter().map(|&v| v as f64 * v as f64).sum();
        let rms = (acc / body.len() as f64).sqrt() as f32;
        let clip = 3.16 * rms;
        for v in body.iter_mut() {
            *v = v.clamp(-clip, clip);
        }
        let c = chirp(&self.cfg);
        let amp = rms * std::f32::consts::SQRT_2;
        let mut out = Vec::with_capacity(
            c.len() + 2 * self.cfg.gap_len() + body.len(),
        );
        out.extend(c.iter().map(|&v| v * amp));
        out.extend(std::iter::repeat(0f32).take(self.cfg.gap_len()));
        out.extend_from_slice(&body);
        out.extend(std::iter::repeat(0f32).take(self.cfg.gap_len()));
        let peak = out.iter().fold(0f32, |m, &v| m.max(v.abs()));
        let scale = self.cfg.headroom / peak.max(1e-9);
        for v in out.iter_mut() {
            *v *= scale;
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ofdm::framing::HEADER_VERSION;
    use crate::ofdm::util::{papr_db, Prng};

    #[test]
    fn packet_papr_within_limit() {
        let cfg = OfdmConfig::default_48k();
        let mut m = Modulator::new(cfg.clone());
        let mut rng = Prng::new(42);
        let bits: Vec<u8> = (0..cfg.bits_per_symbol() * 8)
            .map(|_| (rng.next_u64() & 1) as u8)
            .collect();
        let hdr = PacketHeader {
            version: HEADER_VERSION,
            seq: 0,
            total: 1,
            payload_len: 100,
            modulation: Modulation::Qpsk,
            n_data_symbols: 8,
        };
        let pkt = m.build_packet(&hdr, &bits);
        let body_start = cfg.chirp_len() + cfg.gap_len();
        let body_len = 10 * cfg.symbol_samples();
        let papr = papr_db(&pkt[body_start..body_start + body_len]);
        assert!(papr < 12.0, "papr {}", papr);
        let peak = pkt.iter().fold(0f32, |a, &v| a.max(v.abs()));
        assert!((peak - cfg.headroom).abs() < 1e-3);
    }
}
