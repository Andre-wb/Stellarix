fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(
            tauri_build::AppManifest::new()
                .commands(&[
                    "send_payload_arq",
                    "send_file_arq",
                    "start_listening",
                    "stop_listening",
                ]),
        ),
    )
    .expect("не удалось выполнить tauri-build");
}
