use crate::gf::{gf_mul, gf_poly_mul, gf_pow};

pub(crate) fn rs_generator_poly(nsym: usize) -> Vec<u8> {
    let mut g = vec![1u8];
    for i in 0..nsym {
        g = gf_poly_mul(&g, &[1, gf_pow(2, i as i32)]);
    }
    g
}

pub(crate) fn rs_encode_msg(msg_in: &[u8], nsym: usize) -> Vec<u8> {
    let gen = rs_generator_poly(nsym);
    let mut out = vec![0u8; msg_in.len() + gen.len() - 1];
    out[..msg_in.len()].copy_from_slice(msg_in);
    for i in 0..msg_in.len() {
        let coef = out[i];
        if coef != 0 {
            for j in 1..gen.len() {
                out[i + j] ^= gf_mul(gen[j], coef);
            }
        }
    }
    out[..msg_in.len()].copy_from_slice(msg_in);
    out
}
