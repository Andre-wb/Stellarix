use super::decode::{
    rs_calc_syndromes, rs_correct_errata, rs_find_error_locator, rs_find_errors,
    rs_forney_syndromes,
};

pub(crate) fn rs_correct_msg_erasures(
    msg_in: &[u8],
    nsym: usize,
    erase_pos: &[usize],
) -> Result<Vec<u8>, ()> {
    if erase_pos.len() > nsym {
        return Err(());
    }
    let mut msg_out = msg_in.to_vec();
    for &p in erase_pos {
        if p >= msg_out.len() {
            return Err(());
        }
        msg_out[p] = 0;
    }
    let synd = rs_calc_syndromes(&msg_out, nsym);
    if *synd.iter().max().unwrap() == 0 {
        return Ok(msg_out);
    }
    let fsynd = rs_forney_syndromes(&synd, erase_pos, msg_out.len());
    let err_loc = rs_find_error_locator(&fsynd, nsym, erase_pos.len())?;
    let mut err_loc_rev = err_loc.clone();
    err_loc_rev.reverse();
    let err_pos = rs_find_errors(&err_loc_rev, msg_out.len())?;
    let mut all_pos = erase_pos.to_vec();
    for p in err_pos {
        if !all_pos.contains(&p) {
            all_pos.push(p);
        }
    }
    let corrected = rs_correct_errata(&msg_out, &synd, &all_pos)?;
    let check = rs_calc_syndromes(&corrected, nsym);
    if *check.iter().max().unwrap() > 0 {
        return Err(());
    }
    Ok(corrected)
}

#[cfg(test)]
mod tests {
    use super::rs_correct_msg_erasures;
    use crate::rs::encode::rs_encode_msg;

    fn rng(seed: u32) -> impl FnMut() -> u32 {
        let mut a = seed;
        move || {
            a ^= a << 13;
            a ^= a >> 17;
            a ^= a << 5;
            a
        }
    }

    #[test]
    fn corrects_full_parity_worth_of_erasures() {
        let nsym = 32;
        let mut r = rng(3);
        for _ in 0..200 {
            let k = 8 + (r() as usize % 200);
            let data: Vec<u8> = (0..k).map(|_| (r() & 0xff) as u8).collect();
            let cw = rs_encode_msg(&data, nsym);
            let mut corrupt = cw.clone();
            let mut pos = std::collections::HashSet::new();
            while pos.len() < nsym {
                pos.insert(r() as usize % corrupt.len());
            }
            let erase: Vec<usize> = pos.into_iter().collect();
            for &p in &erase {
                corrupt[p] ^= (1 + (r() & 0xfe)) as u8;
            }
            let dec = rs_correct_msg_erasures(&corrupt, nsym, &erase).expect("should correct");
            assert_eq!(&dec[..k], &data[..]);
        }
    }

    #[test]
    fn corrects_mixed_erasures_and_errors() {
        let nsym = 32;
        let mut r = rng(9);
        for _ in 0..200 {
            let k = 8 + (r() as usize % 200);
            let data: Vec<u8> = (0..k).map(|_| (r() & 0xff) as u8).collect();
            let cw = rs_encode_msg(&data, nsym);
            let mut corrupt = cw.clone();
            let mut pos = std::collections::HashSet::new();
            while pos.len() < 26 {
                pos.insert(r() as usize % corrupt.len());
            }
            let all: Vec<usize> = pos.into_iter().collect();
            let erase = all[..20].to_vec();
            for &p in &all {
                corrupt[p] ^= (1 + (r() & 0xfe)) as u8;
            }
            let dec = rs_correct_msg_erasures(&corrupt, nsym, &erase).expect("should correct");
            assert_eq!(&dec[..k], &data[..]);
        }
    }
}
