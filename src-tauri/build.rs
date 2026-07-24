fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new()
                .commands(&["play_payload", "start_listening", "stop_listening"]),
        ),
    )
    .expect("не удалось выполнить tauri-build");
}
