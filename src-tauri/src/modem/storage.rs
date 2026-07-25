use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

pub fn split_name(name: &str) -> (String, String) {
    match name.rsplit_once('.') {
        Some((s, e)) if !s.is_empty() => (s.to_string(), e.to_string()),
        _ => (name.to_string(), String::new()),
    }
}

pub fn store_unique(dir: &Path, safe_name: &str, content: &[u8]) -> std::io::Result<PathBuf> {
    let (stem, ext) = split_name(safe_name);
    let mut candidate = dir.join(safe_name);
    let mut i = 1;
    while candidate.exists() {
        let alt = if ext.is_empty() {
            format!("{stem} ({i})")
        } else {
            format!("{stem} ({i}).{ext}")
        };
        candidate = dir.join(alt);
        i += 1;
    }
    std::fs::write(&candidate, content)?;
    Ok(candidate)
}

pub fn hash_matches(content: &[u8], expected: &[u8; 32]) -> bool {
    let mut hasher = Sha256::new();
    hasher.update(content);
    hasher.finalize().as_slice() == expected
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    struct TempDir(PathBuf);

    impl TempDir {
        fn new() -> Self {
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let dir = std::env::temp_dir().join(format!(
                "stellarix-storage-{}-{}",
                std::process::id(),
                n
            ));
            std::fs::create_dir_all(&dir).unwrap();
            TempDir(dir)
        }
        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn split_name_separates_stem_and_extension() {
        assert_eq!(split_name("photo.png"), ("photo".into(), "png".into()));
        assert_eq!(split_name("a.b.c"), ("a.b".into(), "c".into()));
        assert_eq!(split_name("noext"), ("noext".into(), String::new()));
        assert_eq!(split_name(".hidden"), (".hidden".into(), String::new()));
    }

    #[test]
    fn store_unique_writes_the_content() {
        let dir = TempDir::new();
        let path = store_unique(dir.path(), "file.txt", b"hello").unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"hello");
        assert_eq!(path.file_name().unwrap(), "file.txt");
    }

    #[test]
    fn store_unique_dedups_with_extension() {
        let dir = TempDir::new();
        let a = store_unique(dir.path(), "doc.pdf", b"1").unwrap();
        let b = store_unique(dir.path(), "doc.pdf", b"2").unwrap();
        let c = store_unique(dir.path(), "doc.pdf", b"3").unwrap();
        assert_eq!(a.file_name().unwrap(), "doc.pdf");
        assert_eq!(b.file_name().unwrap(), "doc (1).pdf");
        assert_eq!(c.file_name().unwrap(), "doc (2).pdf");
        assert_eq!(std::fs::read(&a).unwrap(), b"1");
        assert_eq!(std::fs::read(&b).unwrap(), b"2");
        assert_eq!(std::fs::read(&c).unwrap(), b"3");
    }

    #[test]
    fn store_unique_dedups_without_extension() {
        let dir = TempDir::new();
        let a = store_unique(dir.path(), "README", b"1").unwrap();
        let b = store_unique(dir.path(), "README", b"2").unwrap();
        assert_eq!(a.file_name().unwrap(), "README");
        assert_eq!(b.file_name().unwrap(), "README (1)");
    }

    #[test]
    fn hash_matches_detects_intact_and_corrupt_content() {
        let content = b"the quick brown fox";
        let mut hasher = Sha256::new();
        hasher.update(content);
        let digest: [u8; 32] = hasher.finalize().into();
        assert!(hash_matches(content, &digest));
        assert!(!hash_matches(b"the quick brown fix", &digest));
    }
}
