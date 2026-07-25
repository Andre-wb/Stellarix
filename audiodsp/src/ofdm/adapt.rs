use super::config::Modulation;

const LADDER: [Modulation; 4] = [
    Modulation::Bpsk,
    Modulation::Qpsk,
    Modulation::Qam16,
    Modulation::Qam64,
];

const UP_MARGIN_DB: f32 = 4.0;
const DOWN_MARGIN_DB: f32 = 2.5;
const CLIMB_STREAK: u32 = 2;

fn level_of(m: Modulation) -> usize {
    LADDER.iter().position(|&x| x == m).unwrap_or(0)
}

pub struct RateAdapter {
    level: usize,
    good_streak: u32,
}

impl RateAdapter {
    pub fn new(start: Modulation) -> Self {
        RateAdapter {
            level: level_of(start),
            good_streak: 0,
        }
    }

    pub fn current(&self) -> Modulation {
        LADDER[self.level]
    }

    pub fn observe_failure(&mut self) -> Modulation {
        self.level = self.level.saturating_sub(1);
        self.good_streak = 0;
        self.current()
    }

    pub fn observe_snr(&mut self, snr_db: f32) -> Modulation {
        if LADDER[self.level].required_snr_db() + DOWN_MARGIN_DB > snr_db {
            self.level = self.level.saturating_sub(1);
            self.good_streak = 0;
            return self.current();
        }
        match LADDER.get(self.level + 1) {
            Some(&next) if snr_db >= next.required_snr_db() + UP_MARGIN_DB => {
                self.good_streak += 1;
                if self.good_streak >= CLIMB_STREAK {
                    self.level += 1;
                    self.good_streak = 0;
                }
            }
            _ => self.good_streak = 0,
        }
        self.current()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_at_requested_level() {
        let a = RateAdapter::new(Modulation::Qam16);
        assert_eq!(a.current(), Modulation::Qam16);
    }

    #[test]
    fn climbs_only_after_two_consecutive_good_observations() {
        let mut a = RateAdapter::new(Modulation::Bpsk);
        let snr = Modulation::Qpsk.required_snr_db() + UP_MARGIN_DB;
        assert_eq!(a.observe_snr(snr), Modulation::Bpsk);
        assert_eq!(a.observe_snr(snr), Modulation::Qpsk);
    }

    #[test]
    fn single_bad_observation_resets_climb_streak() {
        let mut a = RateAdapter::new(Modulation::Bpsk);
        let good = Modulation::Qpsk.required_snr_db() + UP_MARGIN_DB;
        assert_eq!(a.observe_snr(good), Modulation::Bpsk);
        assert_eq!(a.observe_snr(good - 10.0), Modulation::Bpsk);
        assert_eq!(a.observe_snr(good), Modulation::Bpsk);
        assert_eq!(a.observe_snr(good), Modulation::Qpsk);
    }

    #[test]
    fn drops_immediately_below_down_margin() {
        let mut a = RateAdapter::new(Modulation::Qam64);
        let low = Modulation::Qam64.required_snr_db() + DOWN_MARGIN_DB - 0.1;
        assert_eq!(a.observe_snr(low), Modulation::Qam16);
    }

    #[test]
    fn failure_drops_one_level_regardless_of_snr() {
        let mut a = RateAdapter::new(Modulation::Qam64);
        let high = Modulation::Qam64.required_snr_db() + 20.0;
        assert_eq!(a.observe_failure(), Modulation::Qam16);
        assert_eq!(a.current(), Modulation::Qam16);
        let _ = high;
    }

    #[test]
    fn never_drops_below_bpsk_or_climbs_above_qam64() {
        let mut a = RateAdapter::new(Modulation::Bpsk);
        assert_eq!(a.observe_failure(), Modulation::Bpsk);
        let mut a = RateAdapter::new(Modulation::Qam64);
        let huge = 200.0;
        a.observe_snr(huge);
        a.observe_snr(huge);
        assert_eq!(a.observe_snr(huge), Modulation::Qam64);
    }

    #[test]
    fn hysteresis_band_prevents_flapping_at_boundary() {
        let mut a = RateAdapter::new(Modulation::Qpsk);
        let boundary = Modulation::Qpsk.required_snr_db() + DOWN_MARGIN_DB + 0.5;
        for _ in 0..10 {
            assert_eq!(a.observe_snr(boundary), Modulation::Qpsk);
        }
    }
}
