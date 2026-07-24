use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter};

use audiodsp::ofdm::OfdmConfig;

use super::capture::{start_capture, Capture};
use super::proto::{self, Frame};

pub enum CtrlWait {
    Ack(u16),
    Nak(u16, Vec<u16>),
    Timeout,
    Stopped,
    Failed(String),
}

pub fn snapshot_at(cap: &Capture, target_fs: u32) -> Vec<f32> {
    let snap = cap.snapshot();
    super::resample::to_rate(&snap, cap.sample_rate, target_fs)
}

pub fn wait_ctrl(
    app: &AppHandle,
    stop: &Arc<AtomicBool>,
    cfg: &OfdmConfig,
    timeout: Duration,
) -> CtrlWait {
    let cap = match start_capture() {
        Ok(c) => c,
        Err(e) => return CtrlWait::Failed(e),
    };
    let started = Instant::now();
    let mut last_len = 0usize;
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
            let snap = snapshot_at(&cap, cfg.fs);
            let res = audiodsp::ofdm::decode_transmission_report(&snap, cfg, None);
            if let Some(payload) = res.payload {
                match proto::parse(&payload) {
                    Some(Frame::Ack { total }) => return CtrlWait::Ack(total),
                    Some(Frame::Nak { total, missing }) => return CtrlWait::Nak(total, missing),
                    _ => {}
                }
            }
        }
        if final_pass {
            return CtrlWait::Timeout;
        }
    }
}
