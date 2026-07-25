pub fn to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_is_empty() {
        assert_eq!(to_hex(&[]), "");
    }

    #[test]
    fn pads_each_byte_to_two_lowercase_digits() {
        assert_eq!(to_hex(&[0x00, 0x0f, 0xa7, 0xff]), "000fa7ff");
        assert_eq!(to_hex(&[0x53]), "53");
    }
}
