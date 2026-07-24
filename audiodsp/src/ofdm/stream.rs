use std::collections::HashMap;

use super::config::{OfdmConfig, MAX_DATA_SYMBOLS};
use super::demodulator::Demodulator;
use super::link::{try_packet, CHIRP_THRESHOLD};
use super::sync::{chirp, find_chirp, refine_by_cp};

pub struct StreamReport {
    pub total: Option<usize>,
    pub parts: HashMap<usize, Vec<u8>>,
    pub consumed: usize,
}

pub fn decode_stream(rx: &[f32], cfg: &OfdmConfig, from: usize) -> StreamReport {
    let template = chirp(cfg);
    let mut demod = Demodulator::new(cfg.clone());
    let sym_len = cfg.symbol_samples();
    let max_packet =
        cfg.chirp_len() + cfg.gap_len() + (2 + MAX_DATA_SYMBOLS) * sym_len + 4 * cfg.cp_len;
    let mut cursor = from.min(rx.len());
    let mut total: Option<usize> = None;
    let mut parts: HashMap<usize, Vec<u8>> = HashMap::new();
    let mut consumed = cursor;
    while cursor + template.len() < rx.len() {
        let found = match find_chirp(&rx[cursor..], &template, CHIRP_THRESHOLD) {
            Some(p) => cursor + p,
            None => {
                consumed = rx.len().saturating_sub(template.len()).max(cursor);
                break;
            }
        };
        let approx = found + cfg.chirp_len() + cfg.gap_len();
        let (train, _) = refine_by_cp(rx, approx, cfg);
        match try_packet(rx, train, &mut demod, cfg) {
            Some((hdr, payload)) => {
                if total.is_none() {
                    total = Some(hdr.total as usize);
                }
                if Some(hdr.total as usize) == total {
                    parts.entry(hdr.seq as usize).or_insert(payload);
                }
                cursor = found
                    + cfg.chirp_len()
                    + cfg.gap_len()
                    + (2 + hdr.n_data_symbols as usize) * sym_len
                    + cfg.gap_len();
                consumed = cursor;
            }
            None => {
                if found + max_packet > rx.len() {
                    consumed = found;
                    break;
                }
                cursor = found + cfg.chirp_len();
                consumed = cursor;
            }
        }
    }
    StreamReport {
        total,
        parts,
        consumed: consumed.min(rx.len()),
    }
}
