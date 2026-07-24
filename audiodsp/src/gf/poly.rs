use super::field::gf_mul;

pub(crate) fn gf_poly_scale(p: &[u8], s: u8) -> Vec<u8> {
    p.iter().map(|&c| gf_mul(c, s)).collect()
}

pub(crate) fn gf_poly_add(p: &[u8], q: &[u8]) -> Vec<u8> {
    let n = p.len().max(q.len());
    let mut r = vec![0u8; n];
    for i in 0..p.len() {
        r[i + n - p.len()] = p[i];
    }
    for i in 0..q.len() {
        r[i + n - q.len()] ^= q[i];
    }
    r
}

pub(crate) fn gf_poly_mul(p: &[u8], q: &[u8]) -> Vec<u8> {
    let mut r = vec![0u8; p.len() + q.len() - 1];
    for j in 0..q.len() {
        for i in 0..p.len() {
            r[i + j] ^= gf_mul(p[i], q[j]);
        }
    }
    r
}

pub(crate) fn gf_poly_eval(p: &[u8], x: u8) -> u8 {
    let mut y = p[0];
    for i in 1..p.len() {
        y = gf_mul(y, x) ^ p[i];
    }
    y
}

pub(crate) fn gf_poly_mod(dividend: &[u8], divisor: &[u8]) -> Vec<u8> {
    let mut out = dividend.to_vec();
    let sep = dividend.len() - (divisor.len() - 1);
    for i in 0..sep {
        let coef = out[i];
        if coef != 0 {
            for j in 1..divisor.len() {
                if divisor[j] != 0 {
                    out[i + j] ^= gf_mul(divisor[j], coef);
                }
            }
        }
    }
    out[sep..].to_vec()
}
