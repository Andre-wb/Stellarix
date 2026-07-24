const MAGIC0: u8 = 0xA7;
const MAGIC1: u8 = 0x53;
const T_MSG: u8 = 1;
const T_FILE: u8 = 2;
const T_NAK: u8 = 3;
const T_ACK: u8 = 4;

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
