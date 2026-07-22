#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend child process (if we started one) so it can be killed
/// when the app window closes. `None` means either it hasn't started yet or
/// we detected an already-running backend and didn't spawn our own.
struct BackendProcess(Mutex<Option<CommandChild>>);

fn backend_already_running() -> bool {
    TcpStream::connect_timeout(&"127.0.0.1:8080".parse().unwrap(), Duration::from_millis(300)).is_ok()
}

/// Locate the Jarvis project root (the directory containing app/main.py).
/// In dev, `tauri dev` runs with cwd = interfaces/desktop, so it's two
/// levels up. Falls back to the known install path for a bundled build run
/// from elsewhere.
fn project_root() -> PathBuf {
    let relative = PathBuf::from("../../");
    if relative.join("app").join("main.py").exists() {
        relative
    } else {
        PathBuf::from(r"C:\Users\HP\Documents\Jarvis")
    }
}

fn main() {
    use std::io::Write;
    eprintln!("[jarvis-desktop] main() starting");
    let _ = std::io::stderr().flush();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            eprintln!("[jarvis-desktop] setup() running");
            let _ = std::io::stderr().flush();

            if backend_already_running() {
                eprintln!("[jarvis-desktop] backend already running on port 8080 — using that instance.");
                let _ = std::io::stderr().flush();
                return Ok(());
            }

            let root = project_root();
            eprintln!("[jarvis-desktop] resolved project root: {:?}", root);
            let _ = std::io::stderr().flush();

            let shell = app.shell();
            let spawn_result = shell
                .command("python")
                .args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8080"])
                .current_dir(root)
                .spawn();

            let (mut rx, child) = match spawn_result {
                Ok(pair) => pair,
                Err(e) => {
                    eprintln!("[jarvis-desktop] FAILED to spawn backend: {:?}", e);
                    let _ = std::io::stderr().flush();
                    return Ok(());
                }
            };
            eprintln!("[jarvis-desktop] backend process spawned, pid={:?}", child.pid());
            let _ = std::io::stderr().flush();

            *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

            // Forward backend stdout/stderr to this process's console so
            // startup errors are visible instead of silently swallowed.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            print!("{}", String::from_utf8_lossy(&line));
                            let _ = std::io::stdout().flush();
                        }
                        CommandEvent::Stderr(line) => {
                            eprint!("{}", String::from_utf8_lossy(&line));
                            let _ = std::io::stderr().flush();
                        }
                        CommandEvent::Error(err) => {
                            eprintln!("[jarvis-desktop] backend command error: {}", err);
                            let _ = std::io::stderr().flush();
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[jarvis-desktop] backend process terminated: {:?}", payload);
                            let _ = std::io::stderr().flush();
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.app_handle().state::<BackendProcess>();
                let child_opt = state.0.lock().unwrap().take();
                if let Some(child) = child_opt {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
