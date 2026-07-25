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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_when_rates_match() {
        let src = vec![0.1, -0.2, 0.3, 0.9];
        assert_eq!(to_rate(&src, 48000, 48000), src);
    }

    #[test]
    fn empty_input_stays_empty() {
        assert!(to_rate(&[], 44100, 48000).is_empty());
    }

    #[test]
    fn downsampling_by_two_halves_length_and_picks_even_samples() {
        let src: Vec<f32> = (0..8).map(|i| i as f32).collect();
        let out = to_rate(&src, 48000, 24000);
        assert_eq!(out.len(), 4);
        assert_eq!(out, vec![0.0, 2.0, 4.0, 6.0]);
    }

    #[test]
    fn upsampling_by_two_doubles_length_and_interpolates_midpoints() {
        let src = vec![0.0, 2.0, 4.0];
        let out = to_rate(&src, 24000, 48000);
        assert_eq!(out.len(), 6);
        for (got, want) in out.iter().zip([0.0, 1.0, 2.0, 3.0, 4.0]) {
            assert!((got - want).abs() < 1e-4, "got {got}, want {want}");
        }
    }

    #[test]
    fn interpolates_linearly_between_neighbours() {
        let src = vec![0.0, 10.0];
        let out = to_rate(&src, 2, 4);
        assert!((out[0] - 0.0).abs() < 1e-4);
        assert!((out[1] - 5.0).abs() < 1e-4);
    }
}
