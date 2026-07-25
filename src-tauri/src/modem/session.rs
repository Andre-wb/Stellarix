use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter};

use audiodsp::ofdm::{Modulation, OfdmConfig};

use super::capture::Capture;
use super::proto::{self, Frame};

pub enum CtrlWait {
    Ack(u16),
    Nak(u16, Vec<u16>),
    Rate {
        seq: u16,
        ok: bool,
        modulation: Modulation,
        snr_db: f32,
    },
    Timeout,
    Stopped,
}

pub fn tail_at(cap: &Capture, target_fs: u32, max_raw_len: usize) -> (Vec<f32>, usize) {
    let (snap, raw_start) = cap.tail(max_raw_len);
    (super::resample::to_rate(&snap, cap.sample_rate, target_fs), raw_start)
}

fn ctrl_rank(ctrl: &CtrlWait) -> u8 {
    match ctrl {
        CtrlWait::Ack(_) => 3,
        CtrlWait::Nak(_, _) => 2,
        CtrlWait::Rate { .. } => 1,
        _ => 0,
    }
}

fn scan_ctrl(snap: &[f32], cfg: &OfdmConfig) -> Option<CtrlWait> {
    let mut best: Option<(u8, usize, CtrlWait)> = None;
    for pkt in audiodsp::ofdm::scan_packets(snap, cfg) {
        let Some(payload) = pkt.payload else { continue };
        let Some(bytes) = audiodsp::ofdm::unpack_payload(&payload, None) else {
            continue;
        };
        let Some(ctrl) = parse_ctrl(&bytes) else { continue };
        let rank = ctrl_rank(&ctrl);
        let better = match &best {
            None => true,
            Some((prev_rank, prev_start, _)) => {
                rank > *prev_rank || (rank == *prev_rank && pkt.start_sample >= *prev_start)
            }
        };
        if better {
            best = Some((rank, pkt.start_sample, ctrl));
        }
    }
    best.map(|(_, _, ctrl)| ctrl)
}

fn parse_ctrl(payload: &[u8]) -> Option<CtrlWait> {
    match proto::parse(payload)? {
        Frame::Ack { total } => Some(CtrlWait::Ack(total)),
        Frame::Nak { total, missing } => Some(CtrlWait::Nak(total, missing)),
        Frame::Rate {
            seq,
            ok,
            modulation,
            snr_db_x10,
        } => Some(CtrlWait::Rate {
            seq,
            ok,
            modulation: Modulation::from_id(modulation)?,
            snr_db: snr_db_x10 as f32 / 10.0,
        }),
        _ => None,
    }
}

pub fn wait_ctrl_on(
    app: &AppHandle,
    stop: &Arc<AtomicBool>,
    cfg: &OfdmConfig,
    cap: &Capture,
    timeout: Duration,
) -> CtrlWait {
    let started = Instant::now();
    let mut last_len = 0usize;
    let max_raw = (cap.sample_rate as f32 * (timeout.as_secs_f32() + 2.0)) as usize;
    loop {
        std::thread::sleep(Duration::from_millis(200));
        let _ = app.emit("modem-level", cap.level());
        if stop.load(Ordering::SeqCst) {
            return CtrlWait::Stopped;
        }
        let final_pass = started.elapsed() >= timeout;
        let len = cap.len();
        if len >= last_len + cfg.fs as usize / 2 || final_pass {
            last_len = len;
            let (snap, _) = tail_at(cap, cfg.fs, max_raw);
            if let Some(ctrl) = scan_ctrl(&snap, cfg) {
                return ctrl;
            }
        }
        if final_pass {
            return CtrlWait::Timeout;
        }
    }
}

pub fn listen_once(cap: &Capture, cfg: &OfdmConfig, window: Duration, tail_seconds: f32) -> Option<CtrlWait> {
    std::thread::sleep(window);
    let max_raw = (cap.sample_rate as f32 * tail_seconds) as usize;
    let (snap, _) = tail_at(cap, cfg.fs, max_raw);
    scan_ctrl(&snap, cfg)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ack() {
        match parse_ctrl(&proto::encode_ack(7)) {
            Some(CtrlWait::Ack(t)) => assert_eq!(t, 7),
            _ => panic!("expected Ack"),
        }
    }

    #[test]
    fn parses_nak_with_missing() {
        match parse_ctrl(&proto::encode_nak(9, &[2, 3])) {
            Some(CtrlWait::Nak(t, m)) => {
                assert_eq!(t, 9);
                assert_eq!(m, vec![2, 3]);
            }
            _ => panic!("expected Nak"),
        }
    }

    #[test]
    fn parses_rate_and_dequantizes_snr() {
        match parse_ctrl(&proto::encode_rate(4, true, Modulation::Qam16.id(), 12.3)) {
            Some(CtrlWait::Rate {
                seq,
                ok,
                modulation,
                snr_db,
            }) => {
                assert_eq!(seq, 4);
                assert!(ok);
                assert_eq!(modulation, Modulation::Qam16);
                assert!((snr_db - 12.3).abs() < 1e-3);
            }
            _ => panic!("expected Rate"),
        }
    }

    #[test]
    fn rejects_rate_with_unknown_modulation_id() {
        assert!(parse_ctrl(&proto::encode_rate(0, true, 7, 5.0)).is_none());
    }

    #[test]
    fn data_frames_are_not_control() {
        assert!(parse_ctrl(&proto::encode_msg(b"hi")).is_none());
        assert!(parse_ctrl(&proto::encode_file("f", &[0u8; 32], b"x")).is_none());
    }

    #[test]
    fn garbage_is_not_control() {
        assert!(parse_ctrl(&[0, 1, 2, 3]).is_none());
        assert!(parse_ctrl(&[]).is_none());
    }

    fn bpsk_cfg() -> OfdmConfig {
        let mut cfg = OfdmConfig::default_48k();
        cfg.modulation = Modulation::Bpsk;
        cfg
    }

    fn wave_of(payload: &[u8]) -> Vec<f32> {
        audiodsp::ofdm::encode_transmission(payload, &bpsk_cfg())
    }

    fn echo_then(payload: &[u8], ctrl: &[u8]) -> Vec<f32> {
        let mut wave = wave_of(payload);
        wave.extend(std::iter::repeat_n(0f32, 4800));
        wave.extend(wave_of(ctrl));
        wave
    }

    #[test]
    fn public_key_payload_fits_one_packet() {
        let cfg = bpsk_cfg();
        let packed = audiodsp::ofdm::pack_payload(&proto::encode_msg(&[7u8; 32]), None);
        assert_eq!(
            audiodsp::ofdm::packed_chunk_count(packed.len(), &cfg),
            1,
            "ключ уходит одним пакетом — эхо отправителя имеет тот же total, что и ACK"
        );
    }

    #[test]
    fn finds_ack_behind_single_packet_echo() {
        let wave = echo_then(&proto::encode_msg(&[7u8; 32]), &proto::encode_ack(1));
        match scan_ctrl(&wave, &OfdmConfig::default_48k()) {
            Some(CtrlWait::Ack(t)) => assert_eq!(t, 1),
            _ => panic!("ACK за эхом однопакетной передачи не найден"),
        }
    }

    #[test]
    fn finds_ack_behind_multi_packet_echo() {
        let wave = echo_then(&proto::encode_msg(&[3u8; 400]), &proto::encode_ack(4));
        match scan_ctrl(&wave, &OfdmConfig::default_48k()) {
            Some(CtrlWait::Ack(t)) => assert_eq!(t, 4),
            _ => panic!("ACK за эхом многопакетной передачи не найден"),
        }
    }

    #[test]
    fn finds_nak_behind_echo() {
        let wave = echo_then(&proto::encode_msg(&[1u8; 200]), &proto::encode_nak(3, &[1]));
        match scan_ctrl(&wave, &OfdmConfig::default_48k()) {
            Some(CtrlWait::Nak(t, miss)) => {
                assert_eq!(t, 3);
                assert_eq!(miss, vec![1]);
            }
            _ => panic!("NAK за эхом не найден"),
        }
    }

    #[test]
    fn own_echo_alone_is_not_control() {
        let wave = wave_of(&proto::encode_msg(&[9u8; 32]));
        assert!(scan_ctrl(&wave, &OfdmConfig::default_48k()).is_none());
    }

    #[test]
    fn ack_wins_over_earlier_rate_frame() {
        let mut wave = wave_of(&proto::encode_rate(0, false, Modulation::Bpsk.id(), 3.0));
        wave.extend(std::iter::repeat_n(0f32, 4800));
        wave.extend(wave_of(&proto::encode_ack(2)));
        match scan_ctrl(&wave, &OfdmConfig::default_48k()) {
            Some(CtrlWait::Ack(t)) => assert_eq!(t, 2),
            _ => panic!("ACK должен побеждать более раннюю оценку канала"),
        }
    }
}
