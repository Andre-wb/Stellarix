use realfft::num_complex::Complex;

use super::constellation;

pub(crate) const BAND_LOW_HZ: f64 = 1000.0;
pub(crate) const BAND_HIGH_HZ: f64 = 7000.0;
pub const MAX_DATA_SYMBOLS: usize = 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Modulation {
    Bpsk,
    Qpsk,
    Qam16,
    Qam64,
}

impl Modulation {
    pub fn bits_per_carrier(&self) -> usize {
        match self {
            Modulation::Bpsk => 1,
            Modulation::Qpsk => 2,
            Modulation::Qam16 => 4,
            Modulation::Qam64 => 6,
        }
    }

    pub fn required_snr_db(&self) -> f32 {
        match self {
            Modulation::Bpsk => 6.0,
            Modulation::Qpsk => 10.0,
            Modulation::Qam16 => 17.0,
            Modulation::Qam64 => 22.0,
        }
    }

    pub fn constellation(&self) -> &'static [Complex<f32>] {
        constellation::table(*self)
    }

    pub(crate) fn id(&self) -> u8 {
        match self {
            Modulation::Bpsk => 0,
            Modulation::Qpsk => 1,
            Modulation::Qam16 => 2,
            Modulation::Qam64 => 3,
        }
    }

    pub(crate) fn from_id(id: u8) -> Option<Modulation> {
        match id {
            0 => Some(Modulation::Bpsk),
            1 => Some(Modulation::Qpsk),
            2 => Some(Modulation::Qam16),
            3 => Some(Modulation::Qam64),
            _ => None,
        }
    }

    pub(crate) fn snr_gate_db(&self) -> f32 {
        match self {
            Modulation::Bpsk => 3.0,
            Modulation::Qpsk => 6.0,
            Modulation::Qam16 => 13.0,
            Modulation::Qam64 => 19.0,
        }
    }

    pub(crate) fn min_dist(&self) -> f32 {
        match self {
            Modulation::Bpsk => 2.0,
            Modulation::Qpsk => 2.0 / 2f32.sqrt(),
            Modulation::Qam16 => 2.0 / 10f32.sqrt(),
            Modulation::Qam64 => 2.0 / 42f32.sqrt(),
        }
    }
}

impl std::str::FromStr for Modulation {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_ascii_lowercase().as_str() {
            "bpsk" => Ok(Modulation::Bpsk),
            "qpsk" => Ok(Modulation::Qpsk),
            "qam16" => Ok(Modulation::Qam16),
            "qam64" => Ok(Modulation::Qam64),
            _ => Err(()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfigError {
    FftSize,
    CpLen,
    Band,
    PilotStride,
    Headroom,
}

#[derive(Clone, Debug)]
pub struct OfdmConfig {
    pub fs: u32,
    pub n_fft: usize,
    pub cp_len: usize,
    pub k_min: usize,
    pub k_max: usize,
    pub pilot_stride: usize,
    pub modulation: Modulation,
    pub headroom: f32,
    pub phase_seed: u64,
}

impl OfdmConfig {
    pub fn for_sample_rate(fs: u32) -> Self {
        let n_fft = 4096usize;
        let k_min = (BAND_LOW_HZ * n_fft as f64 / fs as f64).ceil() as usize;
        let k_max = (BAND_HIGH_HZ * n_fft as f64 / fs as f64).floor() as usize;
        OfdmConfig {
            fs,
            n_fft,
            cp_len: n_fft / 4,
            k_min,
            k_max,
            pilot_stride: 16,
            modulation: Modulation::Qpsk,
            headroom: 0.7,
            phase_seed: 0x0FD3_5EED_C0DE_C0DE,
        }
    }

    pub fn default_48k() -> Self {
        Self::for_sample_rate(48000)
    }

    pub fn n_subcarriers(&self) -> usize {
        self.k_max - self.k_min + 1
    }

    pub fn n_pilots(&self) -> usize {
        (self.n_subcarriers() + self.pilot_stride - 1) / self.pilot_stride
    }

    pub fn n_data_carriers(&self) -> usize {
        self.n_subcarriers() - self.n_pilots()
    }

    pub fn bits_per_symbol(&self) -> usize {
        self.n_data_carriers() * self.modulation.bits_per_carrier()
    }

    pub fn symbol_samples(&self) -> usize {
        self.n_fft + self.cp_len
    }

    pub fn is_pilot(&self, k: usize) -> bool {
        k >= self.k_min && k <= self.k_max && (k - self.k_min) % self.pilot_stride == 0
    }

    pub fn bitrate_raw(&self) -> f32 {
        self.bits_per_symbol() as f32 * self.fs as f32 / self.symbol_samples() as f32
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.n_fft < 64 || !self.n_fft.is_power_of_two() {
            return Err(ConfigError::FftSize);
        }
        if self.cp_len < 4 || self.cp_len >= self.n_fft {
            return Err(ConfigError::CpLen);
        }
        if self.k_min < 2 || self.k_max <= self.k_min || self.k_max >= self.n_fft / 2 {
            return Err(ConfigError::Band);
        }
        if self.pilot_stride < 2 || self.pilot_stride > self.n_subcarriers() {
            return Err(ConfigError::PilotStride);
        }
        if !(self.headroom > 0.0 && self.headroom <= 1.0) {
            return Err(ConfigError::Headroom);
        }
        Ok(())
    }

    pub(crate) fn margin(&self) -> usize {
        self.cp_len / 4
    }

    pub(crate) fn gap_len(&self) -> usize {
        self.n_fft / 2
    }

    pub(crate) fn chirp_len(&self) -> usize {
        self.n_fft
    }
}

#[cfg(test)]
mod tests {
    use super::OfdmConfig;

    #[test]
    fn default_48k_matches_spec() {
        let cfg = OfdmConfig::default_48k();
        cfg.validate().unwrap();
        assert_eq!(cfg.k_min, 86);
        assert_eq!(cfg.k_max, 597);
        assert_eq!(cfg.n_subcarriers(), 512);
        assert_eq!(cfg.n_pilots(), 32);
        assert_eq!(cfg.n_data_carriers(), 480);
        assert_eq!(cfg.symbol_samples(), 5120);
        assert!((cfg.bitrate_raw() - 9000.0).abs() < 1.0);
    }
}
