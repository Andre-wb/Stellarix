pub(crate) struct Prng(u64);

impl Prng {
    pub(crate) fn new(seed: u64) -> Self {
        Prng(seed)
    }

    pub(crate) fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }

    pub(crate) fn next_f32(&mut self) -> f32 {
        (self.next_u64() >> 40) as f32 / (1u64 << 24) as f32
    }
}

pub fn papr_db(samples: &[f32]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let mut peak = 0f32;
    let mut acc = 0f64;
    for &s in samples {
        peak = peak.max(s.abs());
        acc += s as f64 * s as f64;
    }
    if acc == 0.0 {
        return 0.0;
    }
    let rms = (acc / samples.len() as f64).sqrt() as f32;
    20.0 * (peak / rms).log10()
}

pub(crate) fn bytes_to_bits(bytes: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len() * 8);
    for &b in bytes {
        for i in (0..8).rev() {
            out.push((b >> i) & 1);
        }
    }
    out
}

pub(crate) fn bits_to_bytes(bits: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bits.len() / 8);
    for chunk in bits.chunks(8) {
        if chunk.len() < 8 {
            break;
        }
        let mut v = 0u8;
        for &b in chunk {
            v = (v << 1) | (b & 1);
        }
        out.push(v);
    }
    out
}

pub(crate) fn push_bits(out: &mut Vec<u8>, value: u32, width: usize) {
    for i in (0..width).rev() {
        out.push(((value >> i) & 1) as u8);
    }
}

pub(crate) fn read_bits(bits: &[u8], pos: &mut usize, width: usize) -> u32 {
    let mut v = 0u32;
    for _ in 0..width {
        v = (v << 1) | (bits[*pos] & 1) as u32;
        *pos += 1;
    }
    v
}

#[cfg(test)]
mod tests {
    use super::{bits_to_bytes, bytes_to_bits};

    #[test]
    fn bit_byte_roundtrip() {
        let data: Vec<u8> = (0..=255).collect();
        assert_eq!(bits_to_bytes(&bytes_to_bits(&data)), data);
    }
}
