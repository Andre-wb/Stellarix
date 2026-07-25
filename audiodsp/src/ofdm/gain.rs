pub const MIN_GAIN: f32 = 0.25;
pub const MAX_GAIN: f32 = 0.95;
const STEP: f32 = 0.1;

const CLIP_FRAC: f32 = 0.002;
const HOT_PEAK: f32 = 0.8;
const POOR_SNR_DB: f32 = 12.0;
const LOW_PEAK: f32 = 0.2;
const RAISE_SNR_DB: f32 = 8.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GainAdvice {
    Hold,
    Raise,
    Lower,
}

impl GainAdvice {
    pub fn id(self) -> u8 {
        match self {
            GainAdvice::Hold => 0,
            GainAdvice::Raise => 1,
            GainAdvice::Lower => 2,
        }
    }

    pub fn from_id(id: u8) -> GainAdvice {
        match id {
            1 => GainAdvice::Raise,
            2 => GainAdvice::Lower,
            _ => GainAdvice::Hold,
        }
    }
}

pub fn advise_gain(snr_db: f32, clip_ratio: f32, peak: f32) -> GainAdvice {
    if clip_ratio > CLIP_FRAC || (peak > HOT_PEAK && snr_db < POOR_SNR_DB) {
        GainAdvice::Lower
    } else if peak < LOW_PEAK && snr_db < RAISE_SNR_DB {
        GainAdvice::Raise
    } else {
        GainAdvice::Hold
    }
}

pub struct GainController {
    gain: f32,
}

impl GainController {
    pub fn new(start: f32) -> Self {
        GainController {
            gain: start.clamp(MIN_GAIN, MAX_GAIN),
        }
    }

    pub fn current(&self) -> f32 {
        self.gain
    }

    pub fn apply(&mut self, advice: GainAdvice) -> f32 {
        match advice {
            GainAdvice::Raise => self.gain = (self.gain + STEP).min(MAX_GAIN),
            GainAdvice::Lower => self.gain = (self.gain - STEP).max(MIN_GAIN),
            GainAdvice::Hold => {}
        }
        self.gain
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn railing_input_advises_lower_even_when_loud() {
        assert_eq!(advise_gain(4.0, 0.05, 0.99), GainAdvice::Lower);
    }

    #[test]
    fn weak_input_with_poor_snr_advises_raise() {
        assert_eq!(advise_gain(3.0, 0.0, 0.05), GainAdvice::Raise);
    }

    #[test]
    fn healthy_link_holds() {
        assert_eq!(advise_gain(20.0, 0.0, 0.6), GainAdvice::Hold);
    }

    #[test]
    fn loud_but_dirty_link_advises_lower_without_hard_railing() {
        assert_eq!(advise_gain(8.0, 0.0, 0.9), GainAdvice::Lower);
    }

    #[test]
    fn loud_and_clean_link_is_left_alone() {
        assert_eq!(advise_gain(25.0, 0.0, 0.9), GainAdvice::Hold);
    }

    #[test]
    fn quiet_but_decoding_well_holds() {
        assert_eq!(advise_gain(18.0, 0.0, 0.05), GainAdvice::Hold);
    }

    #[test]
    fn clipping_takes_priority_over_weakness_heuristics() {
        assert_eq!(advise_gain(2.0, 0.01, 0.99), GainAdvice::Lower);
    }

    #[test]
    fn advice_survives_a_byte_roundtrip() {
        for a in [GainAdvice::Hold, GainAdvice::Raise, GainAdvice::Lower] {
            assert_eq!(GainAdvice::from_id(a.id()), a);
        }
        assert_eq!(GainAdvice::from_id(200), GainAdvice::Hold);
    }

    #[test]
    fn controller_steps_and_clamps_within_bounds() {
        let mut g = GainController::new(0.6);
        for _ in 0..20 {
            g.apply(GainAdvice::Lower);
        }
        assert!((g.current() - MIN_GAIN).abs() < 1e-6);
        for _ in 0..40 {
            g.apply(GainAdvice::Raise);
        }
        assert!((g.current() - MAX_GAIN).abs() < 1e-6);
    }

    #[test]
    fn controller_clamps_its_starting_point() {
        assert!((GainController::new(5.0).current() - MAX_GAIN).abs() < 1e-6);
        assert!((GainController::new(0.0).current() - MIN_GAIN).abs() < 1e-6);
    }

    #[test]
    fn hold_leaves_gain_unchanged() {
        let mut g = GainController::new(0.6);
        assert!((g.apply(GainAdvice::Hold) - 0.6).abs() < 1e-6);
    }
}
