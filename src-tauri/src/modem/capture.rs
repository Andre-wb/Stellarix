use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, Sample, SampleFormat, SizedSample};

pub struct Capture {
    stop: Arc<AtomicBool>,
    samples: Arc<Mutex<Vec<f32>>>,
    level: Arc<Mutex<f32>>,
    pub sample_rate: u32,
}

impl Capture {
    pub fn level(&self) -> f32 {
        *self.level.lock().unwrap()
    }

    pub fn len(&self) -> usize {
        self.samples.lock().unwrap().len()
    }

    pub fn tail(&self, max_len: usize) -> (Vec<f32>, usize) {
        let buf = self.samples.lock().unwrap();
        let start = buf.len().saturating_sub(max_len);
        (buf[start..].to_vec(), start)
    }
}

impl Drop for Capture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}

pub fn start_capture() -> Result<Capture, String> {
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

    let samples: Arc<Mutex<Vec<f32>>> =
        Arc::new(Mutex::new(Vec::with_capacity(sample_rate as usize * 120)));
    let level = Arc::new(Mutex::new(0f32));
    let stop = Arc::new(AtomicBool::new(false));

    spawn_stream(
        device,
        config,
        format,
        channels,
        samples.clone(),
        level.clone(),
        stop.clone(),
    );

    Ok(Capture {
        stop,
        samples,
        level,
        sample_rate,
    })
}

fn spawn_stream(
    device: cpal::Device,
    config: cpal::StreamConfig,
    format: SampleFormat,
    channels: usize,
    samples: Arc<Mutex<Vec<f32>>>,
    level: Arc<Mutex<f32>>,
    stop: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        let stream = match format {
            SampleFormat::F32 => build::<f32>(&device, config, channels, samples, level),
            SampleFormat::I16 => build::<i16>(&device, config, channels, samples, level),
            SampleFormat::U16 => build::<u16>(&device, config, channels, samples, level),
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
    samples: Arc<Mutex<Vec<f32>>>,
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
                    let mut buf = samples.lock().unwrap();
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
