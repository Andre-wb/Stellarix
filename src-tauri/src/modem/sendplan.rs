pub const MAX_TOTAL_CHUNKS: usize = 4095;

pub fn within_limit(total: usize) -> bool {
    total <= MAX_TOTAL_CHUNKS
}

pub struct PacketRetry {
    retries: usize,
    max: usize,
}

pub enum RetryStep {
    Done,
    Retry,
    GiveUp,
    NoResponse,
}

impl PacketRetry {
    pub fn new(max: usize) -> Self {
        PacketRetry { retries: 0, max }
    }

    pub fn step(&mut self, rate_ok: Option<bool>) -> RetryStep {
        match rate_ok {
            Some(true) => RetryStep::Done,
            Some(false) => {
                self.retries += 1;
                if self.retries >= self.max {
                    RetryStep::GiveUp
                } else {
                    RetryStep::Retry
                }
            }
            None => RetryStep::NoResponse,
        }
    }
}

pub enum CtrlOutcome {
    Ack(usize),
    Nak(usize, Vec<u16>),
    Rate,
    Timeout,
    Stopped,
}

pub enum AckStep {
    Delivered,
    Retransmit,
    GiveUp,
    Stopped,
}

pub struct AckLoop {
    targets: Option<Vec<u16>>,
    full_replays: usize,
    max_full_replays: usize,
    total: usize,
}

impl AckLoop {
    pub fn new(total: usize, max_full_replays: usize, missing: Vec<u16>) -> Self {
        let targets = if missing.is_empty() { None } else { Some(missing) };
        AckLoop {
            targets,
            full_replays: 0,
            max_full_replays,
            total,
        }
    }

    pub fn targets(&self) -> Option<&[u16]> {
        self.targets.as_deref()
    }

    pub fn react(&mut self, outcome: CtrlOutcome) -> AckStep {
        match outcome {
            CtrlOutcome::Ack(t) if t == self.total => AckStep::Delivered,
            CtrlOutcome::Nak(t, miss) if t == self.total => {
                let miss: Vec<u16> = miss
                    .into_iter()
                    .filter(|&s| (s as usize) < self.total)
                    .collect();
                if miss.is_empty() {
                    AckStep::Delivered
                } else {
                    self.targets = Some(miss);
                    AckStep::Retransmit
                }
            }
            CtrlOutcome::Ack(_) | CtrlOutcome::Nak(_, _) | CtrlOutcome::Rate => AckStep::Retransmit,
            CtrlOutcome::Timeout => {
                if self.targets.is_none() {
                    if self.full_replays < self.max_full_replays {
                        self.full_replays += 1;
                        self.targets = Some((0..self.total as u16).collect());
                        AckStep::Retransmit
                    } else {
                        AckStep::GiveUp
                    }
                } else {
                    AckStep::Retransmit
                }
            }
            CtrlOutcome::Stopped => AckStep::Stopped,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn steps(max: usize, replies: &[Option<bool>]) -> Vec<&'static str> {
        let mut r = PacketRetry::new(max);
        replies
            .iter()
            .map(|&x| match r.step(x) {
                RetryStep::Done => "done",
                RetryStep::Retry => "retry",
                RetryStep::GiveUp => "giveup",
                RetryStep::NoResponse => "noresp",
            })
            .collect()
    }

    #[test]
    fn ack_ok_finishes_immediately() {
        assert_eq!(steps(3, &[Some(true)]), vec!["done"]);
    }

    #[test]
    fn no_matching_rate_stops_without_marking_missing() {
        assert_eq!(steps(3, &[None]), vec!["noresp"]);
    }

    #[test]
    fn failures_retry_until_max_then_give_up() {
        assert_eq!(
            steps(3, &[Some(false), Some(false), Some(false)]),
            vec!["retry", "retry", "giveup"]
        );
    }

    #[test]
    fn success_after_a_failure_finishes() {
        assert_eq!(steps(3, &[Some(false), Some(true)]), vec!["retry", "done"]);
    }

    #[test]
    fn max_one_retry_gives_up_on_first_failure() {
        assert_eq!(steps(1, &[Some(false)]), vec!["giveup"]);
    }

    #[test]
    fn ack_for_matching_total_delivers() {
        let mut l = AckLoop::new(5, 1, vec![1, 2]);
        assert!(matches!(l.react(CtrlOutcome::Ack(5)), AckStep::Delivered));
    }

    #[test]
    fn ack_for_wrong_total_is_ignored_and_retransmits() {
        let mut l = AckLoop::new(5, 1, vec![1]);
        assert!(matches!(l.react(CtrlOutcome::Ack(4)), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([1u16].as_slice()));
    }

    #[test]
    fn nak_sets_targets_to_reported_missing() {
        let mut l = AckLoop::new(5, 1, vec![]);
        assert!(matches!(
            l.react(CtrlOutcome::Nak(5, vec![0, 3, 4])),
            AckStep::Retransmit
        ));
        assert_eq!(l.targets(), Some([0u16, 3, 4].as_slice()));
    }

    #[test]
    fn nak_filters_out_of_range_sequences() {
        let mut l = AckLoop::new(3, 1, vec![]);
        assert!(matches!(
            l.react(CtrlOutcome::Nak(3, vec![1, 9, 2, 100])),
            AckStep::Retransmit
        ));
        assert_eq!(l.targets(), Some([1u16, 2].as_slice()));
    }

    #[test]
    fn nak_with_only_out_of_range_sequences_is_treated_as_delivered() {
        let mut l = AckLoop::new(3, 1, vec![]);
        assert!(matches!(
            l.react(CtrlOutcome::Nak(3, vec![7, 8])),
            AckStep::Delivered
        ));
    }

    #[test]
    fn empty_nak_means_delivered() {
        let mut l = AckLoop::new(3, 1, vec![]);
        assert!(matches!(
            l.react(CtrlOutcome::Nak(3, vec![])),
            AckStep::Delivered
        ));
    }

    #[test]
    fn nak_for_wrong_total_is_ignored() {
        let mut l = AckLoop::new(5, 1, vec![2]);
        assert!(matches!(
            l.react(CtrlOutcome::Nak(4, vec![0, 1])),
            AckStep::Retransmit
        ));
        assert_eq!(l.targets(), Some([2u16].as_slice()));
    }

    #[test]
    fn timeout_with_no_targets_triggers_full_replay() {
        let mut l = AckLoop::new(3, 1, vec![]);
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([0u16, 1, 2].as_slice()));
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([0u16, 1, 2].as_slice()));
    }

    #[test]
    fn nak_then_ack_sequence_shrinks_targets_to_delivered() {
        let mut l = AckLoop::new(5, 1, vec![1, 3]);
        assert_eq!(l.targets(), Some([1u16, 3].as_slice()));
        assert!(matches!(
            l.react(CtrlOutcome::Nak(5, vec![3])),
            AckStep::Retransmit
        ));
        assert_eq!(l.targets(), Some([3u16].as_slice()));
        assert!(matches!(l.react(CtrlOutcome::Ack(5)), AckStep::Delivered));
    }

    #[test]
    fn full_replay_persists_targets_across_later_timeouts_until_ack() {
        let mut l = AckLoop::new(2, 1, vec![]);
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([0u16, 1].as_slice()));
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([0u16, 1].as_slice()));
        assert!(matches!(l.react(CtrlOutcome::Ack(2)), AckStep::Delivered));
    }

    #[test]
    fn timeout_with_no_targets_and_no_replays_gives_up() {
        let mut l = AckLoop::new(3, 0, vec![]);
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::GiveUp));
    }

    #[test]
    fn timeout_with_targets_keeps_retransmitting_them() {
        let mut l = AckLoop::new(5, 1, vec![2, 4]);
        assert!(matches!(l.react(CtrlOutcome::Timeout), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([2u16, 4].as_slice()));
    }

    #[test]
    fn rate_noise_is_ignored() {
        let mut l = AckLoop::new(5, 1, vec![1]);
        assert!(matches!(l.react(CtrlOutcome::Rate), AckStep::Retransmit));
        assert_eq!(l.targets(), Some([1u16].as_slice()));
    }

    #[test]
    fn stopped_propagates() {
        let mut l = AckLoop::new(5, 1, vec![]);
        assert!(matches!(l.react(CtrlOutcome::Stopped), AckStep::Stopped));
    }

    #[test]
    fn limit_boundary() {
        assert!(within_limit(MAX_TOTAL_CHUNKS));
        assert!(!within_limit(MAX_TOTAL_CHUNKS + 1));
        assert!(within_limit(1));
    }
}
