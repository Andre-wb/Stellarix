use std::sync::Arc;

use realfft::num_complex::Complex;
use realfft::{RealFftPlanner, RealToComplex};

use crate::consts::{FREQ0, FREQ1};
use crate::window::hann;

pub(super) struct FskSpectrum {
    fft: Arc<dyn RealToComplex<f64>>,
    window: Vec<f64>,
    input: Vec<f64>,
    output: Vec<Complex<f64>>,
    scratch: Vec<Complex<f64>>,
    bin0: usize,
    bin1: usize,
}

impl FskSpectrum {
    pub(super) fn new(bit_samples: usize, sample_rate: u32) -> Self {
        let window = hann(bit_samples);
        let mut planner = RealFftPlanner::<f64>::new();
        let fft = planner.plan_fft_forward(bit_samples);
        let input = fft.make_input_vec();
        let output = fft.make_output_vec();
        let scratch = fft.make_scratch_vec();
        let bin0 = bin_for(bit_samples, sample_rate, FREQ0);
        let bin1 = bin_for(bit_samples, sample_rate, FREQ1);
        Self { fft, window, input, output, scratch, bin0, bin1 }
    }

    pub(super) fn len(&self) -> usize {
        self.window.len()
    }

    pub(super) fn mags(&mut self, samples: &[f32], offset: usize) -> (f64, f64) {
        for (i, slot) in self.input.iter_mut().enumerate() {
            *slot = samples[offset + i] as f64 * self.window[i];
        }
        self.fft
            .process_with_scratch(&mut self.input, &mut self.output, &mut self.scratch)
            .expect("fft buffers sized by planner");
        (self.output[self.bin0].norm(), self.output[self.bin1].norm())
    }
}

fn bin_for(n: usize, sample_rate: u32, freq: f32) -> usize {
    let k = ((n as f64 * freq as f64) / sample_rate as f64).round() as usize;
    k.min(n / 2)
}
