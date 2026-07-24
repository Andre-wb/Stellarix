use crate::rs::{rs_correct_msg, rs_correct_msg_erasures, rs_encode_msg};

pub(crate) const RS_PARITY: usize = 32;
const RS_MAX_DATA: usize = 255 - RS_PARITY;

pub(crate) struct FecLayout {
    pub(crate) n_blocks: usize,
    pub(crate) block_data: usize,
}

impl FecLayout {
    pub(crate) fn for_len(data_len: usize) -> FecLayout {
        let data_len = data_len.max(1);
        let n_blocks = (data_len + RS_MAX_DATA - 1) / RS_MAX_DATA;
        let block_data = (data_len + n_blocks - 1) / n_blocks;
        FecLayout {
            n_blocks,
            block_data,
        }
    }

    pub(crate) fn padded_len(&self) -> usize {
        self.n_blocks * self.block_data
    }

    pub(crate) fn block_len(&self) -> usize {
        self.block_data + RS_PARITY
    }

    pub(crate) fn coded_len(&self) -> usize {
        self.n_blocks * self.block_len()
    }
}

pub(crate) fn encode(data: &[u8]) -> Vec<u8> {
    let l = FecLayout::for_len(data.len());
    let mut padded = data.to_vec();
    padded.resize(l.padded_len(), 0);
    let mut out = vec![0u8; l.coded_len()];
    for (j, chunk) in padded.chunks(l.block_data).enumerate() {
        let cw = rs_encode_msg(chunk, RS_PARITY);
        for (i, &v) in cw.iter().enumerate() {
            out[i * l.n_blocks + j] = v;
        }
    }
    out
}

pub(crate) fn decode(coded: &[u8], data_len: usize, bad: &[bool]) -> Option<Vec<u8>> {
    let l = FecLayout::for_len(data_len);
    if coded.len() < l.coded_len() {
        return None;
    }
    let mut out = Vec::with_capacity(l.padded_len());
    for j in 0..l.n_blocks {
        let mut cw = Vec::with_capacity(l.block_len());
        let mut erase = vec![];
        for i in 0..l.block_len() {
            let p = i * l.n_blocks + j;
            cw.push(coded[p]);
            if bad.get(p).copied().unwrap_or(false) {
                erase.push(i);
            }
        }
        let fixed = if !erase.is_empty() && erase.len() <= RS_PARITY {
            rs_correct_msg_erasures(&cw, RS_PARITY, &erase)
                .or_else(|_| rs_correct_msg(&cw, RS_PARITY))
        } else {
            rs_correct_msg(&cw, RS_PARITY)
        }
        .ok()?;
        out.extend_from_slice(&fixed[..l.block_data]);
    }
    out.truncate(data_len);
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ofdm::util::Prng;

    #[test]
    fn roundtrip_with_erasures_and_errors() {
        let mut rng = Prng::new(11);
        for &len in &[5usize, 200, 900, 2076] {
            let data: Vec<u8> = (0..len).map(|_| (rng.next_u64() & 0xff) as u8).collect();
            let coded = encode(&data);
            let l = FecLayout::for_len(len);
            let mut corrupt = coded.clone();
            let mut bad = vec![false; corrupt.len()];
            for j in 0..l.n_blocks {
                let mut used = std::collections::HashSet::new();
                while used.len() < 25.min(l.block_len()) {
                    used.insert((rng.next_u64() as usize) % l.block_len());
                }
                for (n, &i) in used.iter().enumerate() {
                    let p = i * l.n_blocks + j;
                    corrupt[p] ^= (1 + (rng.next_u64() & 0xfe)) as u8;
                    if n < 20 {
                        bad[p] = true;
                    }
                }
            }
            let got = decode(&corrupt, len, &bad).expect("fec decode failed");
            assert_eq!(got, data, "len {}", len);
        }
    }

    #[test]
    fn clean_roundtrip() {
        let data: Vec<u8> = (0..300).map(|i| (i * 7 % 256) as u8).collect();
        let coded = encode(&data);
        let bad = vec![false; coded.len()];
        assert_eq!(decode(&coded, data.len(), &bad).unwrap(), data);
    }
}
