use std::path::Path;
use std::time::{Duration, Instant};

use tokio::net::TcpListener;
use tracing::{info, warn};

struct StalePid {
    pid: i32,
}

fn read_stale_pid(pg_data: &Path) -> Option<StalePid> {
    let contents = std::fs::read_to_string(pg_data.join("postmaster.pid")).ok()?;
    let pid = contents.lines().next()?.trim().parse::<i32>().ok()?;
    Some(StalePid { pid })
}

async fn addr_in_use(host: &str, port: u16) -> bool {
    match TcpListener::bind((host, port)).await {
        Ok(_) => false,
        Err(e) => e.kind() == std::io::ErrorKind::AddrInUse,
    }
}

async fn port_in_use(port: u16) -> bool {
    addr_in_use("127.0.0.1", port).await || addr_in_use("::1", port).await
}

async fn wait_process_gone(pid: i32, timeout: Duration) -> bool {
    let start = Instant::now();
    loop {
        if !process_alive(pid) {
            return true;
        }
        if start.elapsed() >= timeout {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(150)).await;
    }
}

async fn wait_port_free(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    loop {
        if !port_in_use(port).await {
            return true;
        }
        if start.elapsed() >= timeout {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(150)).await;
    }
}

fn remove_stale_files(pg_data: &Path, port: u16) {
    let _ = std::fs::remove_file(pg_data.join("postmaster.pid"));
    #[cfg(unix)]
    {
        let _ = std::fs::remove_file(format!("/tmp/.s.PGSQL.{port}"));
        let _ = std::fs::remove_file(format!("/tmp/.s.PGSQL.{port}.lock"));
    }
    #[cfg(not(unix))]
    {
        let _ = port;
    }
}

#[cfg(unix)]
fn process_alive(pid: i32) -> bool {
    unsafe {
        libc::kill(pid, 0) == 0
            || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
    }
}

#[cfg(unix)]
fn is_postgres(pid: i32) -> bool {
    if !process_alive(pid) {
        return false;
    }
    match std::process::Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "comm="])
        .output()
    {
        Ok(o) => String::from_utf8_lossy(&o.stdout)
            .to_lowercase()
            .contains("postgres"),
        Err(_) => false,
    }
}

#[cfg(unix)]
fn request_stop(pid: i32) {
    unsafe {
        libc::kill(pid, libc::SIGINT);
    }
}

#[cfg(unix)]
fn force_stop(pid: i32) {
    unsafe {
        libc::kill(pid, libc::SIGKILL);
    }
}

#[cfg(windows)]
fn system_tool(name: &str) -> std::path::PathBuf {
    let root = std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".to_string());
    std::path::Path::new(&root).join("System32").join(name)
}

#[cfg(windows)]
fn tasklist_line(pid: i32) -> String {
    match std::process::Command::new(system_tool("tasklist.exe"))
        .args(["/FI", &format!("PID eq {pid}"), "/NH", "/FO", "CSV"])
        .output()
    {
        Ok(o) => String::from_utf8_lossy(&o.stdout).to_string(),
        Err(_) => String::new(),
    }
}

#[cfg(windows)]
fn process_alive(pid: i32) -> bool {
    let line = tasklist_line(pid);
    !line.contains("No tasks") && line.contains(&pid.to_string())
}

#[cfg(windows)]
fn is_postgres(pid: i32) -> bool {
    tasklist_line(pid).to_lowercase().contains("postgres")
}

#[cfg(windows)]
fn request_stop(pid: i32) {
    force_stop(pid);
}

#[cfg(windows)]
fn force_stop(pid: i32) {
    let _ = std::process::Command::new(system_tool("taskkill.exe"))
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .output();
}

pub async fn free_stale_instance(pg_data: &Path, port: u16) -> Result<(), String> {
    let stale = read_stale_pid(pg_data);

    if !port_in_use(port).await {
        remove_stale_files(pg_data, port);
        return Ok(());
    }

    let stale = stale.ok_or_else(|| {
        format!("Порт {port} занят другим процессом, определить его не удалось. Освободите порт {port} и перезапустите Stellarix.")
    })?;

    if !is_postgres(stale.pid) {
        return Err(format!(
            "Порт {port} занят посторонним процессом (PID {} не является PostgreSQL). Освободите порт {port} и перезапустите Stellarix.",
            stale.pid
        ));
    }

    info!("Обнаружен незавершённый PostgreSQL (PID {}), останавливаю...", stale.pid);
    request_stop(stale.pid);

    if !wait_process_gone(stale.pid, Duration::from_secs(6)).await {
        warn!("PostgreSQL (PID {}) не остановился штатно, принудительная остановка", stale.pid);
        force_stop(stale.pid);
        let _ = wait_process_gone(stale.pid, Duration::from_secs(6)).await;
    }

    if !wait_port_free(port, Duration::from_secs(6)).await {
        return Err(format!(
            "Не удалось освободить порт {port}: процесс PostgreSQL (PID {}) не отпустил его. Закройте процесс вручную и перезапустите.",
            stale.pid
        ));
    }

    remove_stale_files(pg_data, port);
    info!("Порт {port} освобождён, PostgreSQL готов к запуску");
    Ok(())
}

fn parse_pg_major(version_output: &str) -> Option<String> {
    let token = version_output
        .split_whitespace()
        .find(|t| t.chars().next().map_or(false, |c| c.is_ascii_digit()))?;
    let major: String = token.chars().take_while(|c| c.is_ascii_digit()).collect();
    if major.is_empty() {
        None
    } else {
        Some(major)
    }
}

pub fn datadir_version_conflict(pg_data: &Path, binary_dir: &Path) -> Option<(String, String)> {
    let data_major = std::fs::read_to_string(pg_data.join("PG_VERSION"))
        .ok()?
        .trim()
        .to_string();
    if data_major.is_empty() {
        return None;
    }
    let binary = binary_dir.join(if cfg!(windows) { "postgres.exe" } else { "postgres" });
    let output = std::process::Command::new(&binary)
        .arg("--version")
        .output()
        .ok()?;
    let binary_major = parse_pg_major(&String::from_utf8_lossy(&output.stdout))?;
    if data_major != binary_major {
        Some((data_major, binary_major))
    } else {
        None
    }
}

pub fn start_log_tail(pg_data: &Path, max_bytes: usize) -> Option<String> {
    let data = std::fs::read(pg_data.join("start.log")).ok()?;
    if data.is_empty() {
        return None;
    }
    let start = data.len().saturating_sub(max_bytes);
    let tail = String::from_utf8_lossy(&data[start..]).trim().to_string();
    if tail.is_empty() {
        None
    } else {
        Some(tail)
    }
}
