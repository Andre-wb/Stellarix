use crate::gf::{
    gf_div, gf_inverse, gf_mul, gf_poly_add, gf_poly_eval, gf_poly_mod, gf_poly_mul, gf_poly_scale,
    gf_pow,
};

pub(crate) fn rs_calc_syndromes(msg: &[u8], nsym: usize) -> Vec<u8> {
    let mut s = vec![0u8; nsym + 1];
    for i in 0..nsym {
        s[i + 1] = gf_poly_eval(msg, gf_pow(2, i as i32));
    }
    s
}

fn rs_find_errata_locator(e_pos: &[usize]) -> Vec<u8> {
    let mut e = vec![1u8];
    for &i in e_pos {
        e = gf_poly_mul(&e, &gf_poly_add(&[1], &[gf_pow(2, i as i32), 0]));
    }
    e
}

fn rs_find_error_evaluator(synd: &[u8], err_loc: &[u8], nsym: usize) -> Vec<u8> {
    let mul = gf_poly_mul(synd, err_loc);
    let mut divisor = vec![0u8; nsym + 2];
    divisor[0] = 1;
    gf_poly_mod(&mul, &divisor)
}

pub(crate) fn rs_correct_errata(msg_in: &[u8], synd: &[u8], err_pos: &[usize]) -> Result<Vec<u8>, ()> {
    let coef_pos: Vec<usize> = err_pos.iter().map(|&p| msg_in.len() - 1 - p).collect();
    let err_loc = rs_find_errata_locator(&coef_pos);
    let mut synd_rev = synd.to_vec();
    synd_rev.reverse();
    let mut err_eval = rs_find_error_evaluator(&synd_rev, &err_loc, err_loc.len() - 1);
    err_eval.reverse();
    let x: Vec<u8> = coef_pos
        .iter()
        .map(|&cp| gf_pow(2, -((255 - cp) as i32)))
        .collect();
    let mut e = vec![0u8; msg_in.len()];
    for i in 0..x.len() {
        let xi_inv = gf_inverse(x[i]);
        let mut prime: u8 = 1;
        for j in 0..x.len() {
            if j != i {
                prime = gf_mul(prime, 1 ^ gf_mul(xi_inv, x[j]));
            }
        }
        if prime == 0 {
            return Err(());
        }
        let mut err_eval_rev = err_eval.clone();
        err_eval_rev.reverse();
        let mut y = gf_poly_eval(&err_eval_rev, xi_inv);
        y = gf_mul(gf_pow(x[i], 1), y);
        e[err_pos[i]] = gf_div(y, prime);
    }
    Ok(gf_poly_add(msg_in, &e))
}

pub(crate) fn rs_find_error_locator(synd: &[u8], nsym: usize, erase_count: usize) -> Result<Vec<u8>, ()> {
    let mut err_loc = vec![1u8];
    let mut old_loc = vec![1u8];
    let synd_shift = if synd.len() > nsym { synd.len() - nsym } else { 0 };
    for i in 0..(nsym - erase_count) {
        let k = i + synd_shift;
        let mut delta = synd[k];
        for j in 1..err_loc.len() {
            if k >= j {
                delta ^= gf_mul(err_loc[err_loc.len() - 1 - j], synd[k - j]);
            }
        }
        old_loc.push(0);
        if delta != 0 {
            if old_loc.len() > err_loc.len() {
                let new_loc = gf_poly_scale(&old_loc, delta);
                old_loc = gf_poly_scale(&err_loc, gf_inverse(delta));
                err_loc = new_loc;
            }
            err_loc = gf_poly_add(&err_loc, &gf_poly_scale(&old_loc, delta));
        }
    }
    while !err_loc.is_empty() && err_loc[0] == 0 {
        err_loc.remove(0);
    }
    let errs = err_loc.len() as i32 - 1;
    if (errs - erase_count as i32) * 2 + erase_count as i32 > nsym as i32 {
        return Err(());
    }
    Ok(err_loc)
}

pub(crate) fn rs_find_errors(err_loc: &[u8], nmess: usize) -> Result<Vec<usize>, ()> {
    let errs = err_loc.len() - 1;
    let mut pos = vec![];
    for i in 0..nmess {
        if gf_poly_eval(err_loc, gf_pow(2, i as i32)) == 0 {
            pos.push(nmess - 1 - i);
        }
    }
    if pos.len() != errs {
        return Err(());
    }
    Ok(pos)
}

pub(crate) fn rs_forney_syndromes(synd: &[u8], pos: &[usize], nmess: usize) -> Vec<u8> {
    let rev: Vec<usize> = pos.iter().map(|&p| nmess - 1 - p).collect();
    let mut f = synd[1..].to_vec();
    for i in 0..rev.len() {
        let x = gf_pow(2, rev[i] as i32);
        if !f.is_empty() {
            for j in 0..(f.len() - 1) {
                f[j] = gf_mul(f[j], x) ^ f[j + 1];
            }
        }
    }
    f
}

pub(crate) fn rs_correct_msg(msg_in: &[u8], nsym: usize) -> Result<Vec<u8>, ()> {
    let msg_out = msg_in.to_vec();
    let synd = rs_calc_syndromes(&msg_out, nsym);
    if *synd.iter().max().unwrap() == 0 {
        return Ok(msg_out);
    }
    let fsynd = rs_forney_syndromes(&synd, &[], msg_out.len());
    let err_loc = rs_find_error_locator(&fsynd, nsym, 0)?;
    let mut err_loc_rev = err_loc.clone();
    err_loc_rev.reverse();
    let err_pos = rs_find_errors(&err_loc_rev, msg_out.len())?;
    let corrected = rs_correct_errata(&msg_out, &synd, &err_pos)?;
    let check = rs_calc_syndromes(&corrected, nsym);
    if *check.iter().max().unwrap() > 0 {
        return Err(());
    }
    Ok(corrected)
}

#[cfg(test)]
mod tests {
    use super::rs_correct_msg;
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
    fn roundtrip_and_correct_t_errors() {
        let nsym = crate::consts::PKT_NPARITY;
        let t = nsym / 2;
        let mut r = rng(1);
        for _ in 0..3000 {
            let k = 1 + (r() as usize % 20);
            let data: Vec<u8> = (0..k).map(|_| (r() & 0xff) as u8).collect();
            let cw = rs_encode_msg(&data, nsym);
            assert_eq!(&cw[..k], &data[..]);
            let mut corrupt = cw.clone();
            let nerr = (r() as usize) % (t + 1);
            let mut used = std::collections::HashSet::new();
            for _ in 0..nerr {
                let mut p = r() as usize % corrupt.len();
                while used.contains(&p) {
                    p = r() as usize % corrupt.len();
                }
                used.insert(p);
                corrupt[p] ^= (1 + (r() & 0xfe)) as u8;
            }
            let dec = rs_correct_msg(&corrupt, nsym).expect("should correct");
            assert_eq!(&dec[..k], &data[..], "nerr={}", nerr);
        }
    }
}
