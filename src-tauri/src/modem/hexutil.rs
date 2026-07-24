pub fn to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

pub fn from_hex(hex: &str) -> Result<Vec<u8>, String> {
    if !hex.is_ascii() {
        return Err("некорректный hex".to_string());
    }
    if hex.len() % 2 != 0 {
        return Err("нечётная длина hex".to_string());
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&hex[i..i + 2], 16).map_err(|_| "некорректный hex".to_string())
        })
        .collect()
}
