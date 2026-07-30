use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, SampleFormat, SizedSample};

pub struct OutputPlayer {
    device: cpal::Device,
    config: cpal::StreamConfig,
    format: SampleFormat,
    channels: usize,
    sample_rate: u32,
}

impl OutputPlayer {
    pub fn open() -> Result<Self, String> {
        #[cfg(target_os = "android")]
        {
            use ndk_context::android_context;
            android_context();
        }

        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| "Нет устройства вывода звука".to_string())?;
        let supported = device
            .default_output_config()
            .map_err(|e| format!("Конфиг вывода: {e}"))?;
        let sample_rate = supported.sample_rate();
        let channels = supported.channels() as usize;
        let format = supported.sample_format();
        let config = supported.config();
        Ok(OutputPlayer {
            device,
            config,
            format,
            channels,
            sample_rate,
        })
    }

    pub fn play(&self, wave: &[f32], src_fs: u32, stop: &Arc<AtomicBool>) -> Result<(), String> {
        play_chunk(
            &self.device,
            &self.config,
            self.format,
            self.channels,
            wave,
            src_fs,
            self.sample_rate,
            stop,
        )
    }
}

#[allow(clippy::too_many_arguments)]
fn play_chunk(
    device: &cpal::Device,
    config: &cpal::StreamConfig,
    format: SampleFormat,
    channels: usize,
    wave: &[f32],
    src_fs: u32,
    dst_fs: u32,
    stop: &Arc<AtomicBool>,
) -> Result<(), String> {
    let samples = Arc::new(super::resample::to_rate(wave, src_fs, dst_fs));
    let cursor = Arc::new(AtomicUsize::new(0));
    let done = Arc::new((Mutex::new(false), Condvar::new()));

    let stream = match format {
        SampleFormat::F32 => build::<f32>(
            device,
            config.clone(),
            channels,
            samples,
            cursor,
            done.clone(),
        )?,
        SampleFormat::I16 => build::<i16>(
            device,
            config.clone(),
            channels,
            samples,
            cursor,
            done.clone(),
        )?,
        SampleFormat::U16 => build::<u16>(
            device,
            config.clone(),
            channels,
            samples,
            cursor,
            done.clone(),
        )?,
        other => return Err(format!("Неподдерживаемый формат вывода: {other:?}")),
    };
    stream.play().map_err(|e| format!("Запуск вывода: {e}"))?;

    let (lock, cvar) = &*done;
    let mut finished = lock.lock().unwrap();
    while !*finished {
        if stop.load(Ordering::SeqCst) {
            break;
        }
        let (guard, _) = cvar
            .wait_timeout(finished, Duration::from_millis(100))
            .unwrap();
        finished = guard;
    }
    drop(finished);
    drop(stream);
    Ok(())
}

fn build<T>(
    device: &cpal::Device,
    config: cpal::StreamConfig,
    channels: usize,
    samples: Arc<Vec<f32>>,
    cursor: Arc<AtomicUsize>,
    done: Arc<(Mutex<bool>, Condvar)>,
) -> Result<cpal::Stream, String>
where
    T: SizedSample + FromSample<f32>,
{
    let total = samples.len();
    let ch = channels.max(1);
    device
        .build_output_stream(
            config,
            move |data: &mut [T], _: &cpal::OutputCallbackInfo| {
                let frames = data.len() / ch;
                let start = cursor.fetch_add(frames, Ordering::Relaxed);
                for (f, frame) in data.chunks_mut(ch).enumerate() {
                    let s = if start + f < total { samples[start + f] } else { 0.0 };
                    let v = T::from_sample(s);
                    for x in frame.iter_mut() {
                        *x = v;
                    }
                }
                if start + frames >= total {
                    let (lock, cvar) = &*done;
                    if let Ok(mut fin) = lock.lock() {
                        if !*fin {
                            *fin = true;
                            cvar.notify_all();
                        }
                    }
                }
            },
            |e| eprintln!("Ошибка потока вывода: {e}"),
            None,
        )
        .map_err(|e| format!("Создание потока вывода: {e}"))
}
