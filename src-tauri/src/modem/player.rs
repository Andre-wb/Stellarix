use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, SampleFormat, SizedSample};

use audiodsp::ofdm::{
    encode_one_packet, pack_payload, packed_chunk_count, transmission_gap, transmission_lead,
    OfdmConfig, MAX_PACKETS,
};

pub fn play(
    payload: &[u8],
    gain: f32,
    stop: &Arc<AtomicBool>,
    mut progress: impl FnMut(usize, usize),
) -> Result<bool, String> {
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

    let cfg = {
        let mut c = OfdmConfig::default_48k();
        c.headroom = gain.clamp(0.05, 1.0);
        c
    };

    let packed = pack_payload(payload, None);
    let total = packed_chunk_count(packed.len(), &cfg);
    if total > MAX_PACKETS {
        return Err(format!(
            "Файл слишком велик для передачи звуком: {total} пакетов, максимум {MAX_PACKETS}."
        ));
    }
    let lead = transmission_lead(&cfg);
    let inter = transmission_gap(&cfg);

    for seq in 0..total {
        if stop.load(Ordering::SeqCst) {
            return Ok(false);
        }
        progress(seq, total);
        let packet = encode_one_packet(&packed, seq, &cfg)
            .ok_or_else(|| format!("Не удалось собрать пакет {seq}"))?;
        let mut wave = Vec::with_capacity(2 * lead + packet.len() + inter);
        if seq == 0 {
            wave.resize(lead, 0.0);
        }
        wave.extend(packet);
        wave.extend(std::iter::repeat(0f32).take(inter));
        if seq + 1 == total {
            wave.extend(std::iter::repeat(0f32).take(lead));
        }
        play_chunk(
            &device,
            &config,
            format,
            channels,
            &wave,
            cfg.fs,
            sample_rate,
            stop,
        )?;
    }
    Ok(!stop.load(Ordering::SeqCst))
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
