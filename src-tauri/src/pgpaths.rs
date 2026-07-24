use std::path::{Path, PathBuf};

pub fn pg_base_dir(app_data_dir: &Path, identifier: &str) -> PathBuf {
    if path_is_ascii(app_data_dir) {
        return app_data_dir.to_path_buf();
    }
    ascii_fallback_dir(identifier).unwrap_or_else(|| app_data_dir.to_path_buf())
}

fn path_is_ascii(path: &Path) -> bool {
    path.to_str().map(|s| s.is_ascii()).unwrap_or(false)
}

#[cfg(windows)]
fn ascii_fallback_dir(identifier: &str) -> Option<PathBuf> {
    let base = std::env::var_os("ProgramData")
        .map(PathBuf::from)
        .filter(|p| path_is_ascii(p))
        .unwrap_or_else(|| PathBuf::from("C:\\ProgramData"));
    Some(base.join(identifier))
}

#[cfg(not(windows))]
fn ascii_fallback_dir(_identifier: &str) -> Option<PathBuf> {
    None
}
