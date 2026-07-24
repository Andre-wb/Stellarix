use std::sync::LazyLock;

use crate::consts::PRIM;

struct Gf {
    exp: Vec<u16>,
    log: Vec<u16>,
}

static GF: LazyLock<Gf> = LazyLock::new(|| {
    let mut exp = vec![0u16; 512];
    let mut log = vec![0u16; 256];
    let mut x: u32 = 1;
    for i in 0..255usize {
        exp[i] = x as u16;
        log[x as usize] = i as u16;
        x <<= 1;
        if x & 0x100 != 0 {
            x ^= PRIM;
        }
    }
    for i in 255..512usize {
        exp[i] = exp[i - 255];
    }
    Gf { exp, log }
});

pub(crate) fn gf_mul(a: u8, b: u8) -> u8 {
    if a == 0 || b == 0 {
        return 0;
    }
    GF.exp[(GF.log[a as usize] + GF.log[b as usize]) as usize] as u8
}

pub(crate) fn gf_div(a: u8, b: u8) -> u8 {
    if a == 0 {
        return 0;
    }
    let idx = (GF.log[a as usize] as u32 + 255 - GF.log[b as usize] as u32) % 255;
    GF.exp[idx as usize] as u8
}

pub(crate) fn gf_pow(a: u8, power: i32) -> u8 {
    let l = (((GF.log[a as usize] as i32 * power) % 255) + 255) % 255;
    GF.exp[l as usize] as u8
}

pub(crate) fn gf_inverse(a: u8) -> u8 {
    GF.exp[(255 - GF.log[a as usize]) as usize] as u8
}
