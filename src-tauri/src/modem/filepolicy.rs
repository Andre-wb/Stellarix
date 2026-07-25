struct Allowed {
    ext: &'static str,
    mime: &'static str,
    text: bool,
}

const ALLOWED: &[Allowed] = &[
    Allowed { ext: "jpg", mime: "image/jpeg", text: false },
    Allowed { ext: "jpeg", mime: "image/jpeg", text: false },
    Allowed { ext: "jfif", mime: "image/jpeg", text: false },
    Allowed { ext: "png", mime: "image/png", text: false },
    Allowed { ext: "webp", mime: "image/webp", text: false },
    Allowed { ext: "gif", mime: "image/gif", text: false },
    Allowed { ext: "bmp", mime: "image/bmp", text: false },
    Allowed { ext: "pdf", mime: "application/pdf", text: false },
    Allowed { ext: "txt", mime: "text/plain", text: true },
    Allowed { ext: "md", mime: "text/plain", text: true },
    Allowed { ext: "csv", mime: "text/plain", text: true },
    Allowed { ext: "log", mime: "text/plain", text: true },
    Allowed { ext: "json", mime: "application/json", text: true },
];

const DANGEROUS_EXTS: &[&str] = &[
    "php", "php3", "php4", "php5", "phtml", "asp", "aspx", "ascx", "ashx", "jsp", "jspx", "jws",
    "cgi", "pl", "py", "rb", "sh", "bash", "exe", "dll", "bat", "cmd", "ps1", "vbs", "com", "scr",
    "jar", "msi", "app", "dylib", "so", "bin", "run",
];

fn extension_of(name: &str) -> String {
    let base = name.rsplit(['/', '\\']).next().unwrap_or("");
    match base.rfind('.') {
        Some(idx) if idx + 1 < base.len() => base[idx + 1..].to_lowercase(),
        _ => String::new(),
    }
}

fn lookup(ext: &str) -> Option<&'static Allowed> {
    ALLOWED.iter().find(|a| a.ext == ext)
}

pub fn allowed_extensions() -> Vec<&'static str> {
    let mut out = Vec::new();
    for a in ALLOWED {
        if !out.contains(&a.ext) {
            out.push(a.ext);
        }
    }
    out
}

pub fn is_allowed_extension(name: &str) -> bool {
    lookup(&extension_of(name)).is_some()
}

fn has_dangerous_double_extension(name: &str) -> bool {
    let base = name.rsplit(['/', '\\']).next().unwrap_or("");
    let parts: Vec<&str> = base.split('.').collect();
    if parts.len() <= 2 {
        return false;
    }
    parts[1..]
        .iter()
        .any(|p| DANGEROUS_EXTS.contains(&p.to_lowercase().as_str()))
}

fn detect_mime(content: &[u8]) -> Option<&'static str> {
    let b = content;
    if b.starts_with(&[0xFF, 0xD8, 0xFF]) {
        return Some("image/jpeg");
    }
    if b.starts_with(&[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) {
        return Some("image/png");
    }
    if b.starts_with(b"GIF87a") || b.starts_with(b"GIF89a") {
        return Some("image/gif");
    }
    if b.starts_with(b"BM") {
        return Some("image/bmp");
    }
    if b.len() >= 12 && b.starts_with(b"RIFF") && &b[8..12] == b"WEBP" {
        return Some("image/webp");
    }
    if b.starts_with(b"%PDF-") {
        return Some("application/pdf");
    }
    None
}

fn looks_textual(content: &[u8]) -> bool {
    let n = content.len().min(4096);
    if n == 0 {
        return false;
    }
    let sample = &content[..n];
    if sample.contains(&0) {
        return false;
    }
    let bad = sample
        .iter()
        .filter(|&&b| b < 0x09 || (b > 0x0D && b < 0x20))
        .count();
    (bad as f64) / (n as f64) < 0.1
}

pub fn check(name: &str, content: &[u8]) -> Result<&'static str, String> {
    if content.is_empty() {
        return Err("пустой файл".to_string());
    }
    if has_dangerous_double_extension(name) {
        return Err("подозрительное двойное расширение в имени файла".to_string());
    }
    let ext = extension_of(name);
    if ext.is_empty() {
        return Err("у файла нет расширения — формат не определить".to_string());
    }
    let allowed = match lookup(&ext) {
        Some(a) => a,
        None => {
            return Err(format!(
                "формат «.{ext}» не разрешён к передаче; разрешены: {}",
                allowed_extensions().join(", ")
            ))
        }
    };
    if allowed.text {
        if !looks_textual(content) {
            return Err("содержимое не похоже на текст".to_string());
        }
    } else {
        match detect_mime(content) {
            Some(mime) if mime == allowed.mime => {}
            Some(mime) => {
                return Err(format!(
                    "содержимое ({mime}) не совпадает с расширением «.{ext}»"
                ))
            }
            None => {
                return Err(format!(
                    "содержимое не распознано как {} — файл повреждён или подменён",
                    allowed.mime
                ))
            }
        }
    }
    Ok(allowed.mime)
}

#[cfg(test)]
mod tests {
    use super::*;

    const PNG: &[u8] = &[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 0];
    const JPEG: &[u8] = &[0xFF, 0xD8, 0xFF, 0xE0, 0, 0, 0, 0];

    #[test]
    fn accepts_matching_image() {
        assert_eq!(check("photo.png", PNG), Ok("image/png"));
        assert_eq!(check("holiday.jpg", JPEG), Ok("image/jpeg"));
    }

    #[test]
    fn accepts_webp_with_offset_magic() {
        let mut webp = Vec::from(*b"RIFF");
        webp.extend_from_slice(&[0, 0, 0, 0]);
        webp.extend_from_slice(b"WEBPrest");
        assert_eq!(check("pic.webp", &webp), Ok("image/webp"));
    }

    #[test]
    fn accepts_plain_text_by_content() {
        assert_eq!(check("notes.txt", b"hello, world\n"), Ok("text/plain"));
        assert_eq!(check("data.json", b"{\"a\":1}"), Ok("application/json"));
    }

    #[test]
    fn text_with_printable_binary_prefix_is_not_rejected() {
        assert_eq!(check("readme.md", b"BMW cars are great\n"), Ok("text/plain"));
        assert_eq!(check("notes.txt", b"%PDF- is a document format\n"), Ok("text/plain"));
        assert_eq!(check("list.csv", b"GIF89a,is,a,format\n"), Ok("text/plain"));
    }

    #[test]
    fn rejects_disallowed_extension() {
        assert!(check("movie.mp4", &[0, 0, 0, 0]).is_err());
        assert!(check("archive.zip", b"PK\x03\x04").is_err());
    }

    #[test]
    fn rejects_double_extension() {
        assert!(check("invoice.pdf.exe", b"%PDF-1.4").is_err());
        assert!(check("cat.jpg.sh", JPEG).is_err());
    }

    #[test]
    fn rejects_content_extension_mismatch() {
        assert!(check("fake.png", JPEG).is_err());
        assert!(check("trojan.txt", PNG).is_err());
    }

    #[test]
    fn rejects_binary_claiming_text_when_not_textual() {
        assert!(check("weird.txt", &[0u8, 1, 2, 3, 4, 5, 6, 7]).is_err());
    }

    #[test]
    fn rejects_missing_extension_and_empty() {
        assert!(check("noext", JPEG).is_err());
        assert!(check("x.png", &[]).is_err());
    }

    #[test]
    fn extension_helpers_work() {
        assert!(is_allowed_extension("a.PNG"));
        assert!(!is_allowed_extension("a.exe"));
        assert!(allowed_extensions().contains(&"webp"));
    }
}
