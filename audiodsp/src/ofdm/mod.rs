mod adapt;
mod channel_est;
mod config;
mod constellation;
mod demodulator;
mod fec;
mod framing;
mod link;
mod modulator;
mod payload;
mod pilots;
mod sync;
mod util;

pub use adapt::RateAdapter;
pub use channel_est::ChannelEstimate;
pub use config::{ConfigError, Modulation, OfdmConfig, MAX_DATA_SYMBOLS};
pub use demodulator::{Demodulator, SymbolResult};
pub use framing::PacketHeader;
pub use link::{
    decode_transmission, decode_transmission_encrypted, decode_transmission_report,
    encode_one_packet, encode_one_packet_sized, encode_packets_sized, encode_transmission,
    encode_transmission_encrypted, max_packet_payload, max_total_seconds, pack_payload,
    packed_chunk_count, scan_packets, transmission_gap, transmission_lead, unpack_payload,
    DecodeReport, StreamPacket, CHIRP_THRESHOLD, MAX_PACKETS,
};
pub use modulator::Modulator;
pub use sync::{chirp, find_chirp, refine_by_cp, SfoTracker};
pub use util::papr_db;
