use std::net::SocketAddr;
use std::sync::Arc;
use std::thread;
use pyo3::prelude::*;
use tokio::net::UdpSocket;
use tokio::sync::Mutex;
use tokio::time::{self, Duration};
use crate::udp_broadcast::{AppState, PeerInfo, BROADCAST_PORT, BROADCAST_INTERVAL, GLOBAL_STATE};

/// Сигналы соседнему узлу
#[pyfunction]
pub fn start_discovery(name: String, signaling_port: u16) -> PyResult<()> {
    thread::spawn(move || {
        let runtime = match tokio::runtime::Runtime::new() {
            Ok(rt) => rt,
            Err(e) => {
                eprintln!("Ошибка при создании Tokio потока: {}", e);
                return;
            }
        };

        runtime.block_on(async move {
            if let Err(e) = run_discovery(name, signaling_port).await {
                eprintln!("Ошибка при обнаружении пира: {}", e);
            }
        });
    });

    Ok(())
}
/// Обнаружение соседнего узла
async fn run_discovery(
    name: String,
    signaling_port: u16,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {

    let our_info = PeerInfo {
        name,
        signaling_port,
    };

    let send_socket = UdpSocket::bind("0.0.0.0:0").await?;
    send_socket.set_broadcast(true)?;

    let recv_socket = UdpSocket::bind(format!("0.0.0.0:{}", BROADCAST_PORT)).await?;
    let state = Arc::new(Mutex::new(AppState::new(our_info)));
    {
        let mut global = GLOBAL_STATE
            .lock()
            .map_err(|_| "Некорректная глобальная статическая переменная")?;

        *global = Some(state.clone());
    }

    let send_state = state.clone();
    let recv_state = state.clone();

    tokio::spawn(run_sender(send_socket, send_state));
    tokio::spawn(run_receiver(recv_socket, recv_state));

    // Keep task alive forever
    loop {
        tokio::time::sleep(Duration::from_secs(60)).await;
    }
}

async fn run_sender(
    socket: UdpSocket,
    state: Arc<Mutex<AppState>>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {

    let broadcast_addr: SocketAddr =
        format!("255.255.255.255:{}", BROADCAST_PORT).parse()?;

    let mut interval = time::interval(BROADCAST_INTERVAL);

    loop {
        interval.tick().await;

        let info = {
            let state = state.lock().await;
            state.our_info.clone()
        };

        let data = serde_json::to_vec(&info)?;
        socket.send_to(&data, broadcast_addr).await?;
    }
}

async fn run_receiver(
    socket: UdpSocket,
    state: Arc<Mutex<AppState>>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {

    let mut buf = vec![0u8; 1024];

    loop {
        let (size, src_addr) = socket.recv_from(&mut buf).await?;

        if let Ok(info) = serde_json::from_slice::<PeerInfo>(&buf[..size]) {
            let mut state = state.lock().await;
            state.update_peer(src_addr, info);
        }
    }
}

#[pyfunction]
pub fn get_peers() -> PyResult<Vec<(String, u16)>> {
    let global = GLOBAL_STATE
        .lock()
        .map_err(|_| PyErr::new::<pyo3::exceptions::PyValueError, _>("Некорректный Mutex"))?;

    if let Some(state_arc) = &*global {
        let state = state_arc.blocking_lock(); 
        let peers = state.active_peers();

        Ok(peers
            .into_iter()
            .map(|(addr, info)| (addr.ip().to_string(), info.signaling_port))
            .collect())
    } else {
        Ok(vec![])
    }
}