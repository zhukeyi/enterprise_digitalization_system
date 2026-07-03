#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

mod commands;
mod clipboard;
mod shortcuts;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            commands::get_selected_text,
            commands::paste_text,
            commands::get_jwt_token,
            commands::save_jwt_token,
            commands::get_server_url,
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            // Hide initially, show on shortcut
            window.hide().ok();
            shortcuts::register(app.handle())?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Failed to launch FDE AI Assistant");
}