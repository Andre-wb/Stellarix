pub(crate) fn to_rate(src: &[f32], from: u32, to: u32) -> Vec<f32> {
    if from == to {
        return src.to_vec();
    }
    let ratio = from as f64 / to as f64;
    let out_len = (src.len() as f64 / ratio).floor() as usize;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let s = i as f64 * ratio;
        let i0 = s.floor() as usize;
        let frac = (s - i0 as f64) as f32;
        let a = *src.get(i0).unwrap_or(&0.0);
        let b = *src.get(i0 + 1).unwrap_or(&0.0);
        out.push(a + (b - a) * frac);
    }
    out
}
