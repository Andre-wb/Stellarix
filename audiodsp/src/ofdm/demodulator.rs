use std::sync::Arc;

use realfft::num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};

use super::channel_est::{estimate, ChannelEstimate};
use super::config::OfdmConfig;
use super::constellation;
use super::framing::{header_from_soft, PacketHeader};
use super::pilots::{
    correct_by_pilots, phase_randomizer, pilot_values, training_values, PilotFit,
};
use super::sync::SfoTracker;

pub struct SymbolResult {
    pub bits: Vec<u8>,
    pub unreliable: Vec<bool>,
    pub evm_db: f32,
    pub cpe_rad: f32,
    pub timing_slope: f32,
}

pub(crate) struct PacketRx {
    pub(crate) header: PacketHeader,
    pub(crate) bits: Vec<u8>,
    pub(crate) bad_bytes: Vec<usize>,
    pub(crate) sfo: f64,
}

pub struct Demodulator {
    cfg: OfdmConfig,
    fft: Arc<dyn RealToComplex<f32>>,
    input: Vec<f32>,
    spec: Vec<Complex<f32>>,
    scratch: Vec<Complex<f32>>,
    derand: Vec<Complex<f32>>,
    training: Vec<Complex<f32>>,
    pilots: Vec<Complex<f32>>,
}

impl Demodulator {
    pub fn new(cfg: OfdmConfig) -> Self {
        let mut planner = RealFftPlanner::<f32>::new();
        let fft = planner.plan_fft_forward(cfg.n_fft);
        let input = fft.make_input_vec();
        let spec = fft.make_output_vec();
        let scratch = fft.make_scratch_vec();
        let derand: Vec<Complex<f32>> =
            phase_randomizer(&cfg).iter().map(|c| c.conj()).collect();
        let training = training_values(&cfg);
        let pilots = pilot_values(&cfg);
        Demodulator {
            cfg,
            fft,
            input,
            spec,
            scratch,
            derand,
            training,
            pilots,
        }
    }

    pub fn config(&self) -> &OfdmConfig {
        &self.cfg
    }

    pub(crate) fn window_len(&self) -> usize {
        self.cfg.cp_len - self.cfg.margin() + self.cfg.n_fft
    }

    fn spectrum(&mut self, samples: &[f32]) -> bool {
        let off = self.cfg.cp_len - self.cfg.margin();
        let n = self.cfg.n_fft;
        if samples.len() < off + n {
            return false;
        }
        self.input.copy_from_slice(&samples[off..off + n]);
        self.fft
            .process_with_scratch(&mut self.input, &mut self.spec, &mut self.scratch)
            .expect("planned fft sizes");
        true
    }

    pub fn estimate_channel(&mut self, samples: &[f32]) -> ChannelEstimate {
        let ok = self.spectrum(samples);
        assert!(ok, "training slice shorter than fft window");
        estimate(&self.cfg, &self.spec, &self.training)
    }

    fn equalize(&mut self, ch: &ChannelEstimate, derandomize: bool) -> Vec<Complex<f32>> {
        let nsub = self.cfg.n_subcarriers();
        let n0 = ch.noise_power;
        let mut out = Vec::with_capacity(nsub);
        for i in 0..nsub {
            let mut y = self.spec[self.cfg.k_min + i];
            if derandomize {
                y *= self.derand[i];
            }
            let h = ch.h[i];
            out.push(y * h.conj() / (h.norm_sqr() + n0));
        }
        out
    }

    fn equalized_symbol(
        &mut self,
        samples: &[f32],
        ch: &ChannelEstimate,
    ) -> Option<(Vec<Complex<f32>>, PilotFit)> {
        if !self.spectrum(samples) {
            return None;
        }
        let mut eq = self.equalize(ch, true);
        let fit = correct_by_pilots(&mut eq, &self.cfg, &self.pilots, &ch.snr_db);
        Some((eq, fit))
    }

    pub fn decode_header(
        &mut self,
        samples: &[f32],
        ch: &ChannelEstimate,
    ) -> Option<PacketHeader> {
        let (eq, _) = self.equalized_symbol(samples, ch)?;
        let mut soft = Vec::with_capacity(self.cfg.n_data_carriers());
        for (i, v) in eq.iter().enumerate() {
            if i % self.cfg.pilot_stride != 0 {
                soft.push(v.re);
            }
        }
        header_from_soft(&soft)
    }

    pub fn decode_symbol(
        &mut self,
        samples: &[f32],
        ch: &ChannelEstimate,
        _symbol_index: usize,
    ) -> SymbolResult {
        let (eq, fit) = self
            .equalized_symbol(samples, ch)
            .expect("symbol slice shorter than fft window");
        let m = self.cfg.modulation;
        let bpc = m.bits_per_carrier();
        let gate_snr = m.snr_gate_db();
        let gate_evm = 0.5 * m.min_dist();
        let mut bits = Vec::with_capacity(self.cfg.bits_per_symbol());
        let mut unreliable = Vec::with_capacity(self.cfg.n_data_carriers());
        let mut evm_acc = 0f64;
        for (i, v) in eq.iter().enumerate() {
            if i % self.cfg.pilot_stride == 0 {
                continue;
            }
            let (idx, dist) = constellation::demap(m, *v);
            constellation::push_index_bits(idx, bpc, &mut bits);
            evm_acc += dist as f64 * dist as f64;
            unreliable.push(ch.snr_db[i] < gate_snr || dist > gate_evm);
        }
        let nd = self.cfg.n_data_carriers();
        let evm_db = (10.0 * (evm_acc / nd as f64).max(1e-12).log10()) as f32;
        SymbolResult {
            bits,
            unreliable,
            evm_db,
            cpe_rad: fit.cpe,
            timing_slope: fit.slope,
        }
    }

    pub fn receive_packet(
        &mut self,
        rx: &[f32],
        start: usize,
    ) -> Option<(PacketHeader, Vec<u8>, Vec<usize>)> {
        self.receive_packet_full(rx, start)
            .map(|r| (r.header, r.bits, r.bad_bytes))
    }

    pub(crate) fn receive_packet_full(&mut self, rx: &[f32], start: usize) -> Option<PacketRx> {
        let sym_len = self.cfg.symbol_samples();
        let wl = self.window_len();
        if start + wl > rx.len() {
            return None;
        }
        let ch = self.estimate_channel(&rx[start..]);
        if ch.mean_snr_db < 3.0 {
            return None;
        }
        let hpos = start + sym_len;
        if hpos + wl > rx.len() {
            return None;
        }
        let header = self.decode_header(&rx[hpos..], &ch)?;
        let saved = self.cfg.modulation;
        self.cfg.modulation = header.modulation;
        let bpc = header.modulation.bits_per_carrier();
        let mut tracker = SfoTracker::new(&self.cfg);
        let mut bits = Vec::new();
        let mut bitbad = Vec::new();
        let mut complete = true;
        for s in 0..header.n_data_symbols as usize {
            let m = s + 2;
            let pos = tracker.position(start, m);
            if pos + wl > rx.len() {
                complete = false;
                break;
            }
            let res = self.decode_symbol(&rx[pos..], &ch, s);
            let applied = pos as f64 - (start as f64 + m as f64 * sym_len as f64);
            let delta = tracker.slope_to_delta(res.timing_slope) + applied;
            tracker.record(m, delta);
            for &f in &res.unreliable {
                for _ in 0..bpc {
                    bitbad.push(f);
                }
            }
            bits.extend_from_slice(&res.bits);
        }
        self.cfg.modulation = saved;
        if !complete {
            return None;
        }
        let mut bad_bytes = vec![];
        for byte_i in 0..bits.len() / 8 {
            if bitbad[byte_i * 8..byte_i * 8 + 8].iter().any(|&b| b) {
                bad_bytes.push(byte_i);
            }
        }
        Some(PacketRx {
            header,
            bits,
            bad_bytes,
            sfo: tracker.estimate(),
        })
    }
}
