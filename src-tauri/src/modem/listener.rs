use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, Sample, SampleFormat, SizedSample};
use tauri::{AppHandle, Emitter};

#[derive(Clone, serde::Serialize)]
struct Packets {
    have: usize,
    total: usize,
}

pub struct Listener {
    stop: Arc<AtomicBool>,
}

impl Listener {
    pub fn signal_stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}

pub fn start(app: AppHandle) -> Result<Listener, String> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or_else(|| "Нет доступного микрофона".to_string())?;
    let supported = device
        .default_input_config()
        .map_err(|e| format!("Конфиг микрофона: {e}"))?;
    let sample_rate = supported.sample_rate();
    let channels = supported.channels() as usize;
    let format = supported.sample_format();
    let config = supported.config();

    let captured: Arc<Mutex<Vec<f32>>> = Arc::new(Mutex::new(Vec::with_capacity(sample_rate as usize * 120)));
    let level = Arc::new(Mutex::new(0f32));
    let stop = Arc::new(AtomicBool::new(false));

    spawn_capture(device, config, format, channels, captured.clone(), level.clone(), stop.clone());
    spawn_decoder(app, sample_rate, captured, level, stop.clone());

    Ok(Listener { stop })
}

fn spawn_capture(
    device: cpal::Device,
    config: cpal::StreamConfig,
    format: SampleFormat,
    channels: usize,
    captured: Arc<Mutex<Vec<f32>>>,
    level: Arc<Mutex<f32>>,
    stop: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        let stream = match format {
            SampleFormat::F32 => build::<f32>(&device, config.clone(), channels, captured.clone(), level.clone()),
            SampleFormat::I16 => build::<i16>(&device, config.clone(), channels, captured.clone(), level.clone()),
            SampleFormat::U16 => build::<u16>(&device, config.clone(), channels, captured.clone(), level.clone()),
            other => Err(format!("Неподдерживаемый формат микрофона: {other:?}")),
        };
        let stream = match stream {
            Ok(s) => s,
            Err(e) => {
                eprintln!("{e}");
                return;
            }
        };
        if let Err(e) = stream.play() {
            eprintln!("Запуск микрофона: {e}");
            return;
        }
        while !stop.load(Ordering::SeqCst) {
            std::thread::sleep(Duration::from_millis(100));
        }
        drop(stream);
    });
}

fn build<T>(
    device: &cpal::Device,
    config: cpal::StreamConfig,
    channels: usize,
    captured: Arc<Mutex<Vec<f32>>>,
    level: Arc<Mutex<f32>>,
) -> Result<cpal::Stream, String>
where
    T: SizedSample,
    f32: FromSample<T>,
{
    let ch = channels.max(1);
    device
        .build_input_stream(
            config,
            move |data: &[T], _: &cpal::InputCallbackInfo| {
                let mut sum = 0f32;
                let mut cnt = 0f32;
                {
                    let mut buf = captured.lock().unwrap();
                    for frame in data.chunks(ch) {
                        let s: f32 = f32::from_sample(frame[0]);
                        buf.push(s);
                        sum += s * s;
                        cnt += 1.0;
                    }
                }
                if cnt > 0.0 {
                    let rms = (sum / cnt).sqrt();
                    let mut l = level.lock().unwrap();
                    *l = *l * 0.7 + rms * 0.3;
                }
            },
            |e| eprintln!("Ошибка потока микрофона: {e}"),
            None,
        )
        .map_err(|e| format!("Создание потока микрофона: {e}"))
}

fn spawn_decoder(
    app: AppHandle,
    sample_rate: u32,
    captured: Arc<Mutex<Vec<f32>>>,
    level: Arc<Mutex<f32>>,
    stop: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        let cfg = audiodsp::ofdm::OfdmConfig::default_48k();
        let started = Instant::now();
        let timeout =
            Duration::from_secs_f32(audiodsp::ofdm::max_total_seconds(&cfg) * 2.0 + 30.0);
        let interval = sample_rate as usize * 4;
        let mut last_len = 0usize;
        let mut decoded = false;
        let mut user_stop = false;
        loop {
            std::thread::sleep(Duration::from_millis(250));
            let cur_level = *level.lock().unwrap();
            let _ = app.emit("modem-level", cur_level);
            let timed_out = started.elapsed() >= timeout;
            user_stop = stop.load(Ordering::SeqCst);
            let stopping = user_stop || timed_out;
            let len = captured.lock().unwrap().len();
            if stopping || len >= last_len + interval {
                last_len = len;
                let snapshot = captured.lock().unwrap().clone();
                let snapshot = super::resample::to_rate(&snapshot, sample_rate, cfg.fs);
                let res = audiodsp::ofdm::decode_transmission_report(&snapshot, &cfg, None);
                if let Some(payload) = res.payload {
                    let hex: String = payload.iter().map(|b| format!("{:02x}", b)).collect();
                    let _ = app.emit("modem-decoded", hex);
                    decoded = true;
                    break;
                } else if let Some(total) = res.total {
                    let _ = app.emit("modem-packets", Packets { have: res.have, total });
                }
            }
            if stopping {
                break;
            }
        }
        stop.store(true, Ordering::SeqCst);
        if !decoded {
            if user_stop {
                let _ = app.emit("modem-stopped", "Приём остановлен.".to_string());
            } else {
                let _ = app.emit(
                    "modem-error",
                    "Не удалось распознать сигнал. Сблизьте устройства и увеличьте громкость.".to_string(),
                );
            }
        }
    });
}
