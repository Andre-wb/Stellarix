use audiodsp::ofdm::{
    decode_transmission, encode_one_packet_sized, encode_transmission, max_packet_payload,
    pack_payload, packed_chunk_count, scan_packets, transmission_gap, transmission_lead,
    unpack_payload, Modulation, OfdmConfig, RateAdapter,
};

fn rng(seed: u64) -> impl FnMut() -> u64 {
    let mut s = seed;
    move || {
        s = s.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = s;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
}

fn rand_bytes(r: &mut impl FnMut() -> u64, n: usize) -> Vec<u8> {
    (0..n).map(|_| (r() & 0xff) as u8).collect()
}

fn add_awgn(rx: &mut [f32], r: &mut impl FnMut() -> u64, sigma: f32) {
    for v in rx.iter_mut() {
        let u = (r() >> 40) as f32 / (1u64 << 24) as f32;
        *v += (u * 2.0 - 1.0) * sigma * 1.732;
    }
}

fn active_rms(x: &[f32]) -> f32 {
    let mut acc = 0f64;
    let mut n = 0usize;
    for &v in x {
        if v.abs() > 0.0 {
            acc += v as f64 * v as f64;
            n += 1;
        }
    }
    ((acc / n.max(1) as f64).sqrt()) as f32
}

#[test]
fn required_snr_ladder_is_conservative_at_each_modulation() {
    for m in [
        Modulation::Bpsk,
        Modulation::Qpsk,
        Modulation::Qam16,
        Modulation::Qam64,
    ] {
        let mut cfg = OfdmConfig::default_48k();
        cfg.modulation = m;
        let mut seed = rng(4200 + m.bits_per_carrier() as u64);
        let payload = rand_bytes(&mut seed, 700);
        let tx = encode_transmission(&payload, &cfg);
        let rms = active_rms(&tx);
        let target_db = m.required_snr_db() + 4.0;
        let sigma = rms / 10f32.powf(target_db / 20.0);
        for trial in 0..8u64 {
            let mut r = rng(9000 + m.bits_per_carrier() as u64 * 1000 + trial);
            let mut rx = tx.clone();
            add_awgn(&mut rx, &mut r, sigma);
            assert_eq!(
                decode_transmission(&rx, &cfg).as_deref(),
                Some(payload.as_slice()),
                "{:?} failed to decode at required_snr_db()+4dB (trial {trial})",
                m
            );
        }
    }
}

#[test]
fn adapter_never_settles_on_a_modulation_that_then_fails_to_decode() {
    for target_db in (4..=32).step_by(2) {
        let mut adapter = RateAdapter::new(Modulation::Bpsk);
        for _ in 0..8 {
            adapter.observe_snr(target_db as f32);
        }
        let picked = adapter.current();

        let mut cfg = OfdmConfig::default_48k();
        cfg.modulation = picked;
        let mut seed = rng(1000 + target_db as u64);
        let payload = rand_bytes(&mut seed, 600);
        let tx = encode_transmission(&payload, &cfg);
        let rms = active_rms(&tx);
        let sigma = rms / 10f32.powf(target_db as f32 / 20.0);

        for trial in 0..6u64 {
            let mut r = rng(50_000 + target_db as u64 * 100 + trial);
            let mut rx = tx.clone();
            add_awgn(&mut rx, &mut r, sigma);
            assert_eq!(
                decode_transmission(&rx, &cfg).as_deref(),
                Some(payload.as_slice()),
                "adapter picked {:?} at target {target_db}dB but decode failed (trial {trial})",
                picked
            );
        }
    }
}

#[test]
fn mixed_modulation_stream_decodes_with_a_fixed_bpsk_sized_chunk() {
    let mut sizing_cfg = OfdmConfig::default_48k();
    sizing_cfg.modulation = Modulation::Bpsk;
    let chunk_max = max_packet_payload(&sizing_cfg).max(1);

    let mut seed = rng(777);
    let payload = rand_bytes(&mut seed, chunk_max * 3 + chunk_max / 2);
    let packed = pack_payload(&payload, None);
    let total = packed_chunk_count(packed.len(), &sizing_cfg);
    assert!(total >= 3, "test needs a multi-packet payload, got {total}");

    let ladder = [
        Modulation::Bpsk,
        Modulation::Qpsk,
        Modulation::Qam16,
        Modulation::Qam64,
    ];
    let cfg = OfdmConfig::default_48k();
    let lead = transmission_lead(&cfg);
    let inter = transmission_gap(&cfg);
    let mut wave = vec![0f32; lead];
    let mut expected_modulation = Vec::with_capacity(total);
    for seq in 0..total {
        let m = ladder[seq % ladder.len()];
        expected_modulation.push(m);
        let mut pkt_cfg = cfg.clone();
        pkt_cfg.modulation = m;
        let pkt = encode_one_packet_sized(&packed, seq, total, chunk_max, &pkt_cfg)
            .expect("packet should encode");
        wave.extend(pkt);
        wave.extend(std::iter::repeat_n(0f32, inter));
    }
    wave.extend(std::iter::repeat_n(0f32, lead));

    let found = scan_packets(&wave, &cfg);
    assert_eq!(found.len(), total, "expected every packet to be found");

    let mut by_seq = vec![None; total];
    for pkt in found {
        let seq = pkt.header.seq as usize;
        assert_eq!(
            pkt.header.modulation, expected_modulation[seq],
            "packet {seq} decoded with the wrong modulation"
        );
        assert!(pkt.payload.is_some(), "packet {seq} failed to decode cleanly");
        by_seq[seq] = pkt.payload;
    }

    let mut reassembled = Vec::new();
    for chunk in by_seq {
        reassembled.extend(chunk.expect("every seq should have been found"));
    }
    assert_eq!(unpack_payload(&reassembled, None).unwrap(), payload);
}

#[test]
fn adapter_climbs_and_falls_back_across_a_full_sweep() {
    let mut adapter = RateAdapter::new(Modulation::Bpsk);
    let mut seen_qam64 = false;
    for _ in 0..10 {
        adapter.observe_snr(35.0);
    }
    if adapter.current() == Modulation::Qam64 {
        seen_qam64 = true;
    }
    assert!(seen_qam64, "adapter should reach Qam64 on a very clean channel");

    for _ in 0..4 {
        adapter.observe_snr(2.0);
    }
    assert_eq!(
        adapter.current(),
        Modulation::Bpsk,
        "adapter should fall all the way back on a very noisy channel"
    );
}
