use std::collections::HashMap;
use std::net::SocketAddr;
use std::time::Duration;
use serde::{Deserialize, Serialize};
use tokio::time;
use once_cell::sync::Lazy;
use std::sync::{Mutex, Arc};

static GLOBAL_STATE: Lazy<Mutex<Option<Arc<tokio::sync::Mutex<AppState>>>>> = Lazy::new(|| Mutex::new(None));

pub mod discovery;

const BROADCAST_PORT: u16 = 4200;
const BROADCAST_INTERVAL: Duration = Duration::from_secs(2);
#[allow(unused)]
const PEER_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
struct PeerInfo {
    name: String,
    signaling_port: u16,
}

impl PeerInfo {
    #[allow(unused)]
    fn new(name: String, signaling_port: u16) -> Self {
        Self { name, signaling_port }
    }
}

#[derive(Debug, Clone)]
struct Peer {
    info: PeerInfo,
    last_seen: time::Instant,
}

impl Peer {
    #[allow(unused)]
    fn new(info: PeerInfo, last_seen: time::Instant) -> Self {
        Peer { info, last_seen }
    }
}

struct AppState {
    peers: HashMap<SocketAddr, Peer>,
    our_info: PeerInfo,
}

impl AppState {
    fn new(our_info: PeerInfo) -> Self {
        Self {
            peers: HashMap::new(),
            our_info,
        }
    }
    fn update_peer(&mut self, addr: SocketAddr, info: PeerInfo) {
        self.peers.insert(
            addr,
            Peer {
                info,
                last_seen: time::Instant::now(),
            }
        );
    }
    #[allow(unused)]
    fn remove_stale_peers(&mut self) {
        let now = time::Instant::now();
        self.peers.retain(|_, peer| now.duration_since(peer.last_seen) < PEER_TIMEOUT);
    }

    fn active_peers(&self) -> Vec<(SocketAddr, PeerInfo)> {
        self.peers.iter().map(|(addr, peer)| (*addr, peer.info.clone())).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use std::time::Duration as StdDuration;

    // Вспомогательная функция для создания тестовых адресов
    fn test_addr(ip: u8, port: u16) -> SocketAddr {
        SocketAddr::from(([127, 0, 0, ip], port))
    }

    // Константные тестовые данные
    const TEST_PEERS: [(u8, u16, &str, u16); 3] = [
        (1, 4201, "Alice", 9001),
        (2, 4202, "Bob", 9002),
        (3, 4203, "Charlie", 9003),
    ];

    // Функция для получения тестовых данных (вычисляется во время выполнения)
    fn get_test_data() -> Vec<(SocketAddr, PeerInfo)> {
        TEST_PEERS.iter().map(|(ip, port, name, sig_port)| {
            (test_addr(*ip, *port), PeerInfo::new(name.to_string(), *sig_port))
        }).collect()
    }

    #[test]
    fn test_peer_actions() -> Result<(), ()> {
        let peer_info = PeerInfo {
            name: String::from("User"),
            signaling_port: 9001,
        };

        let mut app = AppState::new(peer_info.clone());

        let socketaddr = SocketAddr::from(([127, 0, 0, 1], BROADCAST_PORT));
        app.update_peer(socketaddr, peer_info.clone());

        assert_eq!(app.peers.get(&socketaddr).unwrap().info, peer_info);

        let active_peers = app.active_peers();
        assert_eq!(active_peers.len(), 1);
        assert_eq!(active_peers[0].0, socketaddr);
        assert_eq!(active_peers[0].1, peer_info);

        Ok(())
    }

    #[test]
    fn test_peer_info_new() {
        let info = PeerInfo::new("Test User".to_string(), 9001);
        assert_eq!(info.name, "Test User");
        assert_eq!(info.signaling_port, 9001);
    }

    #[test]
    fn test_peer_new() {
        let info = PeerInfo::new("Test Peer".to_string(), 9001);
        let now = time::Instant::now();
        let peer = Peer::new(info.clone(), now);

        assert_eq!(peer.info, info);
        assert_eq!(peer.last_seen, now);
    }

    #[test]
    fn test_app_state_new() {
        let our_info = PeerInfo::new("TestUser".to_string(), 9000);
        let app = AppState::new(our_info.clone());

        assert_eq!(app.our_info, our_info);
        assert!(app.peers.is_empty());
        assert_eq!(app.active_peers().len(), 0);
    }

    #[test]
    fn test_update_peer_add_new() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr = test_addr(1, 4201);
        let peer_info = PeerInfo::new("Alice".to_string(), 9001);

        app.update_peer(addr, peer_info.clone());

        assert_eq!(app.peers.len(), 1);
        let peer = app.peers.get(&addr).unwrap();
        assert_eq!(peer.info, peer_info);
        assert!(peer.last_seen <= time::Instant::now());
    }

    #[test]
    fn test_update_peer_update_existing() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr = test_addr(1, 4201);
        let peer_info = PeerInfo::new("Alice".to_string(), 9001);

        app.update_peer(addr, peer_info);
        let first_seen = app.peers.get(&addr).unwrap().last_seen;

        // Немного ждем, чтобы время изменилось
        thread::sleep(StdDuration::from_millis(10));

        let updated_info = PeerInfo::new("Alice Updated".to_string(), 9002);
        app.update_peer(addr, updated_info.clone());

        assert_eq!(app.peers.len(), 1);
        let peer = app.peers.get(&addr).unwrap();
        assert_eq!(peer.info, updated_info);
        assert!(peer.last_seen > first_seen);
    }

    #[test]
    fn test_update_peer_multiple_peers() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let test_data = get_test_data();

        for (addr, info) in test_data.iter() {
            app.update_peer(*addr, info.clone());
        }

        assert_eq!(app.peers.len(), 3);

        for (addr, info) in test_data {
            assert_eq!(app.peers.get(&addr).unwrap().info, info);
        }
    }

    #[test]
    fn test_remove_stale_peers() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr1 = test_addr(1, 4201);
        let addr2 = test_addr(2, 4202);

        app.update_peer(addr1, PeerInfo::new("Fresh".to_string(), 9001));
        app.update_peer(addr2, PeerInfo::new("Stale".to_string(), 9002));

        #[cfg(test)]
        {
            if let Some(peer) = app.peers.get_mut(&addr2) {
                peer.last_seen = time::Instant::now() - PEER_TIMEOUT - Duration::from_secs(1);
            }
        }

        app.remove_stale_peers();

        assert_eq!(app.peers.len(), 1);
        assert!(app.peers.contains_key(&addr1));
        assert!(!app.peers.contains_key(&addr2));
    }

    #[test]
    fn test_active_peers_empty() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let app = AppState::new(our_info);

        let active = app.active_peers();
        assert!(active.is_empty());
        assert_eq!(active.len(), 0);
    }

    #[test]
    fn test_active_peers_with_data() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let test_data = get_test_data();

        for (addr, info) in test_data.iter() {
            app.update_peer(*addr, info.clone());
        }

        let active = app.active_peers();
        assert_eq!(active.len(), 3);

        let active_map: HashMap<SocketAddr, PeerInfo> = active.into_iter().collect();

        for (addr, expected_info) in test_data {
            assert_eq!(active_map.get(&addr).unwrap(), &expected_info);
        }
    }

    #[test]
    fn test_active_peers_returns_clone() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr = test_addr(1, 4201);
        let peer_info = PeerInfo::new("Alice".to_string(), 9001);

        app.update_peer(addr, peer_info.clone());

        let active = app.active_peers();

        // Изменяем исходные данные
        if let Some(peer) = app.peers.get_mut(&addr) {
            peer.info = PeerInfo::new("Changed".to_string(), 9999);
        }

        assert_eq!(active[0].1, peer_info, "active_peers должен возвращать копию");
    }

    #[test]
    fn test_peer_info_serialization() {
        let info = PeerInfo::new("Test User".to_string(), 9001);

        let serialized = serde_json::to_string(&info).unwrap();
        assert!(serialized.contains("Test User"));
        assert!(serialized.contains("9001"));

        let deserialized: PeerInfo = serde_json::from_str(&serialized).unwrap();
        assert_eq!(deserialized, info);
    }

    #[test]
    fn test_constants() {
        assert_eq!(BROADCAST_PORT, 4200);
        assert_eq!(BROADCAST_INTERVAL, Duration::from_secs(2));
        assert_eq!(PEER_TIMEOUT, Duration::from_secs(10));
    }

    #[test]
    fn test_update_peer_same_addr_multiple_times() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr = test_addr(1, 4201);

        for i in 0..5 {
            let info = PeerInfo::new(format!("Version{}", i), 9000 + i);
            app.update_peer(addr, info);
            assert_eq!(app.peers.len(), 1, "Должен быть только один пир");
        }
    }

    #[test]
    fn test_last_seen_updates_correctly() {
        let our_info = PeerInfo::new("Me".to_string(), 9000);
        let mut app = AppState::new(our_info);

        let addr = test_addr(1, 4201);
        let peer_info = PeerInfo::new("Alice".to_string(), 9001);

        app.update_peer(addr, peer_info);
        let first_seen = app.peers.get(&addr).unwrap().last_seen;

        // Имитируем прошедшее время
        thread::sleep(StdDuration::from_millis(50));

        app.update_peer(addr, PeerInfo::new("Alice".to_string(), 9001));
        let second_seen = app.peers.get(&addr).unwrap().last_seen;

        assert!(second_seen > first_seen);
        assert!(second_seen.duration_since(first_seen).as_millis() >= 50);
    }
}