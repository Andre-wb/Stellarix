use std::collections::{HashMap, HashSet};

pub enum Ingest {
    Stale,
    WrongTotal,
    Duplicate,
    Accepted,
}

#[derive(Default)]
pub struct Reassembler {
    parts: HashMap<usize, Vec<u8>>,
    resolved: HashSet<usize>,
    watermark: usize,
    total: Option<usize>,
}

impl Reassembler {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn total(&self) -> Option<usize> {
        self.total
    }

    pub fn have(&self) -> usize {
        self.parts.len()
    }

    pub fn has_parts(&self) -> bool {
        !self.parts.is_empty()
    }

    pub fn ingest(&mut self, abs: usize, seq: usize, hdr_total: usize) -> Ingest {
        if abs <= self.watermark {
            return Ingest::Stale;
        }
        if self.total.is_none() {
            self.total = Some(hdr_total);
        }
        if self.total != Some(hdr_total) {
            return Ingest::WrongTotal;
        }
        self.watermark = abs;
        if self.resolved.contains(&seq) {
            return Ingest::Duplicate;
        }
        Ingest::Accepted
    }

    pub fn store(&mut self, seq: usize, payload: Vec<u8>) {
        self.parts.insert(seq, payload);
        self.resolved.insert(seq);
    }

    pub fn is_complete(&self) -> bool {
        matches!(self.total, Some(t) if self.parts.len() >= t)
    }

    pub fn assemble(&self) -> Vec<u8> {
        let t = self.total.unwrap_or(0);
        let mut packed = Vec::new();
        for s in 0..t {
            if let Some(part) = self.parts.get(&s) {
                packed.extend_from_slice(part);
            }
        }
        packed
    }

    pub fn missing_list(&self, cap: usize) -> Vec<u16> {
        let t = self.total.unwrap_or(0);
        (0..t)
            .filter(|s| !self.parts.contains_key(s))
            .map(|s| s as u16)
            .take(cap)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn accept(r: &mut Reassembler, abs: usize, seq: usize, total: usize, payload: &[u8]) {
        assert!(matches!(r.ingest(abs, seq, total), Ingest::Accepted));
        r.store(seq, payload.to_vec());
    }

    #[test]
    fn locks_total_on_first_packet() {
        let mut r = Reassembler::new();
        assert!(r.total().is_none());
        assert!(matches!(r.ingest(10, 0, 3), Ingest::Accepted));
        assert_eq!(r.total(), Some(3));
    }

    #[test]
    fn stale_packet_below_watermark_is_skipped() {
        let mut r = Reassembler::new();
        assert!(matches!(r.ingest(100, 0, 3), Ingest::Accepted));
        assert!(matches!(r.ingest(100, 1, 3), Ingest::Stale));
        assert!(matches!(r.ingest(50, 1, 3), Ingest::Stale));
    }

    #[test]
    fn packet_with_different_total_is_rejected_without_advancing_watermark() {
        let mut r = Reassembler::new();
        assert!(matches!(r.ingest(10, 0, 3), Ingest::Accepted));
        assert!(matches!(r.ingest(20, 1, 5), Ingest::WrongTotal));
        assert!(matches!(r.ingest(20, 1, 3), Ingest::Accepted));
    }

    #[test]
    fn already_resolved_sequence_is_a_duplicate_but_advances_watermark() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 3, b"a");
        assert!(matches!(r.ingest(20, 0, 3), Ingest::Duplicate));
        assert!(matches!(r.ingest(20, 1, 3), Ingest::Stale));
        assert!(matches!(r.ingest(30, 1, 3), Ingest::Accepted));
    }

    #[test]
    fn failed_packet_not_stored_can_be_retried_later() {
        let mut r = Reassembler::new();
        assert!(matches!(r.ingest(10, 1, 3), Ingest::Accepted));
        assert!(matches!(r.ingest(20, 1, 3), Ingest::Accepted));
    }

    #[test]
    fn completeness_tracks_total() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 2, b"x");
        assert!(!r.is_complete());
        accept(&mut r, 20, 1, 2, b"y");
        assert!(r.is_complete());
    }

    #[test]
    fn assemble_concatenates_in_sequence_order() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 2, 3, b"C");
        accept(&mut r, 20, 0, 3, b"A");
        accept(&mut r, 30, 1, 3, b"B");
        assert_eq!(r.assemble(), b"ABC");
    }

    #[test]
    fn missing_list_reports_absent_sequences() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 4, b"x");
        accept(&mut r, 30, 2, 4, b"z");
        assert_eq!(r.missing_list(500), vec![1u16, 3]);
    }

    #[test]
    fn missing_list_respects_cap() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 6, b"x");
        assert_eq!(r.missing_list(2), vec![1u16, 2]);
    }

    #[test]
    fn have_counts_stored_payloads_only() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 3, b"x");
        assert!(matches!(r.ingest(20, 1, 3), Ingest::Accepted));
        assert_eq!(r.have(), 1);
    }

    #[test]
    fn nak_round_completes_after_missing_packet_is_resent() {
        let mut r = Reassembler::new();
        accept(&mut r, 10, 0, 2, b"A");
        assert!(matches!(r.ingest(20, 1, 2), Ingest::Accepted));
        assert_eq!(r.have(), 1);
        assert_eq!(r.missing_list(500), vec![1u16]);
        assert!(!r.is_complete());

        assert!(matches!(r.ingest(20, 0, 2), Ingest::Stale));
        accept(&mut r, 30, 1, 2, b"B");
        assert_eq!(r.have(), 2);
        assert!(r.missing_list(500).is_empty());
        assert!(r.is_complete());
        assert_eq!(r.assemble(), b"AB");
    }
}
