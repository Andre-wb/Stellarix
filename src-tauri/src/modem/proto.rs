const MAGIC0: u8 = 0xA7;
const MAGIC1: u8 = 0x53;
const T_MSG: u8 = 1;
const T_FILE: u8 = 2;
const T_NAK: u8 = 3;
const T_ACK: u8 = 4;
const T_RATE: u8 = 5;

pub enum Frame {
    Msg(Vec<u8>),
    File {
        name: String,
        sha256: [u8; 32],
        content: Vec<u8>,
    },
    Nak {
        total: u16,
        missing: Vec<u16>,
    },
    Ack {
        total: u16,
    },
    Rate {
        seq: u16,
        ok: bool,
        modulation: u8,
        snr_db_x10: i16,
    },
}

pub fn encode_msg(body: &[u8]) -> Vec<u8> {
    let mut out = vec![MAGIC0, MAGIC1, T_MSG];
    out.extend_from_slice(body);
    out
}

pub fn encode_file(name: &str, sha256: &[u8; 32], content: &[u8]) -> Vec<u8> {
    let name_bytes = name.as_bytes();
    let mut out = vec![MAGIC0, MAGIC1, T_FILE];
    out.extend_from_slice(&(name_bytes.len() as u16).to_be_bytes());
    out.extend_from_slice(name_bytes);
    out.extend_from_slice(sha256);
    out.extend_from_slice(content);
    out
}

pub fn encode_nak(total: u16, missing: &[u16]) -> Vec<u8> {
    let mut out = vec![MAGIC0, MAGIC1, T_NAK];
    out.extend_from_slice(&total.to_be_bytes());
    out.extend_from_slice(&(missing.len() as u16).to_be_bytes());
    for m in missing {
        out.extend_from_slice(&m.to_be_bytes());
    }
    out
}

pub fn encode_ack(total: u16) -> Vec<u8> {
    let mut out = vec![MAGIC0, MAGIC1, T_ACK];
    out.extend_from_slice(&total.to_be_bytes());
    out
}

pub fn encode_rate(seq: u16, ok: bool, modulation: u8, snr_db: f32) -> Vec<u8> {
    let mut out = vec![MAGIC0, MAGIC1, T_RATE];
    out.extend_from_slice(&seq.to_be_bytes());
    out.push(if ok { 1 } else { 0 });
    out.push(modulation);
    let snr_db_x10 = (snr_db * 10.0).round().clamp(i16::MIN as f32, i16::MAX as f32) as i16;
    out.extend_from_slice(&snr_db_x10.to_be_bytes());
    out
}

pub fn parse(data: &[u8]) -> Option<Frame> {
    if data.len() < 3 || data[0] != MAGIC0 || data[1] != MAGIC1 {
        return None;
    }
    let body = &data[3..];
    match data[2] {
        T_MSG => Some(Frame::Msg(body.to_vec())),
        T_FILE => {
            if body.len() < 2 {
                return None;
            }
            let name_len = u16::from_be_bytes([body[0], body[1]]) as usize;
            let rest = &body[2..];
            if rest.len() < name_len + 32 {
                return None;
            }
            let name = String::from_utf8(rest[..name_len].to_vec()).ok()?;
            let mut sha = [0u8; 32];
            sha.copy_from_slice(&rest[name_len..name_len + 32]);
            Some(Frame::File {
                name,
                sha256: sha,
                content: rest[name_len + 32..].to_vec(),
            })
        }
        T_NAK => {
            if body.len() < 4 {
                return None;
            }
            let total = u16::from_be_bytes([body[0], body[1]]);
            let count = u16::from_be_bytes([body[2], body[3]]) as usize;
            let rest = &body[4..];
            if rest.len() < count * 2 {
                return None;
            }
            let missing = (0..count)
                .map(|i| u16::from_be_bytes([rest[i * 2], rest[i * 2 + 1]]))
                .collect();
            Some(Frame::Nak { total, missing })
        }
        T_ACK => {
            if body.len() < 2 {
                return None;
            }
            Some(Frame::Ack {
                total: u16::from_be_bytes([body[0], body[1]]),
            })
        }
        T_RATE => {
            if body.len() < 6 {
                return None;
            }
            Some(Frame::Rate {
                seq: u16::from_be_bytes([body[0], body[1]]),
                ok: body[2] != 0,
                modulation: body[3],
                snr_db_x10: i16::from_be_bytes([body[4], body[5]]),
            })
        }
        _ => None,
    }
}

pub fn sanitize_filename(name: &str) -> String {
    let base = name.rsplit(['/', '\\']).next().unwrap_or("");
    let cleaned: String = base
        .chars()
        .filter(|c| !c.is_control() && !matches!(c, '<' | '>' | ':' | '"' | '|' | '?' | '*'))
        .collect();
    let trimmed = cleaned.trim().trim_start_matches('.').to_string();
    if trimmed.is_empty() {
        "received.bin".to_string()
    } else {
        trimmed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn msg_roundtrips() {
        let body = b"hello world";
        match parse(&encode_msg(body)) {
            Some(Frame::Msg(b)) => assert_eq!(b, body),
            _ => panic!("expected Msg"),
        }
    }

    #[test]
    fn file_roundtrips_with_name_hash_and_content() {
        let sha = [7u8; 32];
        let content = b"binary\x00\xff payload";
        match parse(&encode_file("photo.png", &sha, content)) {
            Some(Frame::File {
                name,
                sha256,
                content: c,
            }) => {
                assert_eq!(name, "photo.png");
                assert_eq!(sha256, sha);
                assert_eq!(c, content);
            }
            _ => panic!("expected File"),
        }
    }

    #[test]
    fn file_with_empty_content_roundtrips() {
        let sha = [0u8; 32];
        match parse(&encode_file("a", &sha, b"")) {
            Some(Frame::File { name, content, .. }) => {
                assert_eq!(name, "a");
                assert!(content.is_empty());
            }
            _ => panic!("expected File"),
        }
    }

    #[test]
    fn nak_roundtrips_with_missing_list() {
        let missing = vec![0u16, 5, 4094];
        match parse(&encode_nak(12, &missing)) {
            Some(Frame::Nak { total, missing: m }) => {
                assert_eq!(total, 12);
                assert_eq!(m, missing);
            }
            _ => panic!("expected Nak"),
        }
    }

    #[test]
    fn empty_nak_roundtrips() {
        match parse(&encode_nak(3, &[])) {
            Some(Frame::Nak { total, missing }) => {
                assert_eq!(total, 3);
                assert!(missing.is_empty());
            }
            _ => panic!("expected Nak"),
        }
    }

    #[test]
    fn ack_roundtrips() {
        match parse(&encode_ack(4095)) {
            Some(Frame::Ack { total }) => assert_eq!(total, 4095),
            _ => panic!("expected Ack"),
        }
    }

    #[test]
    fn rate_roundtrips_and_quantizes_snr() {
        match parse(&encode_rate(9, true, 2, 13.37)) {
            Some(Frame::Rate {
                seq,
                ok,
                modulation,
                snr_db_x10,
            }) => {
                assert_eq!(seq, 9);
                assert!(ok);
                assert_eq!(modulation, 2);
                assert_eq!(snr_db_x10, 134);
            }
            _ => panic!("expected Rate"),
        }
    }

    #[test]
    fn rate_carries_negative_snr_and_not_ok() {
        match parse(&encode_rate(1, false, 0, -6.25)) {
            Some(Frame::Rate {
                ok, snr_db_x10, ..
            }) => {
                assert!(!ok);
                assert_eq!(snr_db_x10, -63);
            }
            _ => panic!("expected Rate"),
        }
    }

    #[test]
    fn rate_clamps_extreme_snr() {
        match parse(&encode_rate(0, true, 0, 100000.0)) {
            Some(Frame::Rate { snr_db_x10, .. }) => assert_eq!(snr_db_x10, i16::MAX),
            _ => panic!("expected Rate"),
        }
        match parse(&encode_rate(0, true, 0, -100000.0)) {
            Some(Frame::Rate { snr_db_x10, .. }) => assert_eq!(snr_db_x10, i16::MIN),
            _ => panic!("expected Rate"),
        }
    }

    #[test]
    fn rejects_bad_magic() {
        assert!(parse(&[0x00, 0x53, T_MSG]).is_none());
        assert!(parse(&[0xA7, 0x00, T_MSG]).is_none());
    }

    #[test]
    fn rejects_too_short() {
        assert!(parse(&[]).is_none());
        assert!(parse(&[0xA7]).is_none());
        assert!(parse(&[0xA7, 0x53]).is_none());
    }

    #[test]
    fn rejects_unknown_type() {
        assert!(parse(&[MAGIC0, MAGIC1, 99]).is_none());
    }

    #[test]
    fn rejects_file_truncated_before_name_and_hash_complete() {
        let full = encode_file("name", &[1u8; 32], b"body");
        let header_min = 3 + 2 + "name".len() + 32;
        for cut in 3..header_min {
            assert!(
                parse(&full[..cut]).is_none(),
                "a File cut to {cut} bytes lacks a complete name+hash and must not parse"
            );
        }
        assert!(matches!(parse(&full), Some(Frame::File { .. })));
    }

    #[test]
    fn rejects_file_with_invalid_utf8_name() {
        let mut frame = vec![MAGIC0, MAGIC1, T_FILE];
        frame.extend_from_slice(&2u16.to_be_bytes());
        frame.extend_from_slice(&[0xff, 0xfe]);
        frame.extend_from_slice(&[0u8; 32]);
        assert!(parse(&frame).is_none());
    }

    #[test]
    fn rejects_truncated_nak_frame() {
        let full = encode_nak(5, &[1, 2, 3]);
        for cut in 3..full.len() {
            assert!(
                parse(&full[..cut]).is_none(),
                "a Nak claiming 3 missing must not parse from {cut} bytes"
            );
        }
        assert!(matches!(parse(&full), Some(Frame::Nak { .. })));
    }

    #[test]
    fn rejects_short_ack() {
        assert!(parse(&[MAGIC0, MAGIC1, T_ACK, 0x00]).is_none());
    }

    #[test]
    fn rejects_short_rate() {
        assert!(parse(&[MAGIC0, MAGIC1, T_RATE, 0, 0, 0]).is_none());
    }

    #[test]
    fn sanitize_strips_directory_components() {
        assert_eq!(sanitize_filename("/etc/passwd"), "passwd");
        assert_eq!(sanitize_filename("..\\..\\windows\\system32\\x.dll"), "x.dll");
        assert_eq!(sanitize_filename("a/b/c/report.pdf"), "report.pdf");
    }

    #[test]
    fn sanitize_removes_forbidden_and_control_characters() {
        assert_eq!(sanitize_filename("na<me>:\"|?*.txt"), "name.txt");
        assert_eq!(sanitize_filename("a\u{0007}b\u{0000}c.dat"), "abc.dat");
    }

    #[test]
    fn sanitize_trims_and_drops_leading_dots() {
        assert_eq!(sanitize_filename("  spaced.txt  "), "spaced.txt");
        assert_eq!(sanitize_filename("...hidden"), "hidden");
    }

    #[test]
    fn sanitize_falls_back_when_empty() {
        assert_eq!(sanitize_filename(""), "received.bin");
        assert_eq!(sanitize_filename("///"), "received.bin");
        assert_eq!(sanitize_filename("<<<>>>"), "received.bin");
        assert_eq!(sanitize_filename("..."), "received.bin");
    }
}
