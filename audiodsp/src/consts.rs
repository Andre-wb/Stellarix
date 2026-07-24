pub(crate) const FREQ0: f32 = 1800.0;
pub(crate) const FREQ1: f32 = 5500.0;
pub(crate) const BIT_DURATION: f32 = 0.06;
pub(crate) const PREAMBLE: [u8; 21] = [
    1, 0, 1, 0, 1, 0, 1, 0, 1, 1,
    0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0,
];
pub(crate) const GAP_SECONDS: f32 = 0.1;
pub(crate) const SILENCE_BEFORE: f32 = 0.3;
pub(crate) const SILENCE_AFTER: f32 = 0.4;
pub const MAX_PAYLOAD_LEN: usize = 96;
pub(crate) const PKT_CHUNK: usize = 4;
pub(crate) const PKT_NPARITY: usize = 16;
pub(crate) const PKT_HEADER: usize = 3;
pub(crate) const PKT_BYTES: usize = PKT_HEADER + PKT_CHUNK + PKT_NPARITY;
pub const PLAYBACK_GAIN: f32 = 0.6;
pub(crate) const PRIM: u32 = 0x11D;
