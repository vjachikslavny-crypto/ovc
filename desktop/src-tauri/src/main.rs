#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Context, Result};
use tauri::{Manager, RunEvent, WindowUrl};

const LOCAL_HOST: &str = "127.0.0.1";
const LOCAL_PORT: u16 = 18741;

struct BackendState {
    child: Mutex<Option<Child>>,
}

fn find_project_root() -> Result<PathBuf> {
    let current = std::env::current_dir().context("failed to read current dir")?;
    if current.join("src").exists() && current.join("scripts").exists() {
        return Ok(current);
    }

    let exe = std::env::current_exe().context("failed to read current exe")?;
    for ancestor in exe.ancestors() {
        if ancestor.join("src").exists() && ancestor.join("scripts").exists() {
            return Ok(ancestor.to_path_buf());
        }
    }

    Err(anyhow!("cannot find OVC project root"))
}

fn ensure_dir(path: &Path) -> Result<()> {
    if !path.exists() {
        std::fs::create_dir_all(path).with_context(|| format!("failed to create {}", path.display()))?;
    }
    Ok(())
}

fn wait_for_port(host: &str, port: u16, timeout: Duration) -> bool {
    let started = Instant::now();
    while started.elapsed() < timeout {
        if TcpStream::connect((host, port)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(250));
    }
    false
}

fn spawn_local_backend(app_data_dir: &Path) -> Result<Child> {
    let root = find_project_root()?;
    let db_path = app_data_dir.join("ovc-desktop.db");
    let database_url = format!("sqlite:///{}", db_path.display());

    let mut cmd = Command::new("python3");
    cmd.arg("-m")
        .arg("uvicorn")
        .arg("app.main:app")
        .arg("--app-dir")
        .arg("src")
        .arg("--host")
        .arg(LOCAL_HOST)
        .arg("--port")
        .arg(LOCAL_PORT.to_string())
        .current_dir(root)
        .env("PYTHONPATH", "src")
        .env("DATABASE_URL", database_url)
        .env("DESKTOP_MODE", "1")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    let child = cmd.spawn().context("failed to start local backend")?;
    Ok(child)
}

fn main() {
    let state = BackendState {
        child: Mutex::new(None),
    };

    let app = tauri::Builder::default()
        .manage(state)
        .setup(|app| {
            let base_url = std::env::var("OVC_DESKTOP_BASE_URL").unwrap_or_default();
            let target_url = if base_url.trim().is_empty() {
                let app_data_dir = app
                    .path_resolver()
                    .app_data_dir()
                    .unwrap_or_else(|| std::env::temp_dir().join("ovc-desktop"));
                ensure_dir(&app_data_dir)?;

                let child = spawn_local_backend(&app_data_dir)?;
                {
                    let mut guard = app.state::<BackendState>().child.lock().expect("poisoned mutex");
                    *guard = Some(child);
                }

                if !wait_for_port(LOCAL_HOST, LOCAL_PORT, Duration::from_secs(25)) {
                    return Err(anyhow!("local backend did not start in time").into());
                }

                format!("http://{}:{}", LOCAL_HOST, LOCAL_PORT)
            } else {
                base_url
            };

            let parsed = url::Url::parse(&target_url)
                .with_context(|| format!("invalid target URL: {}", target_url))?;

            tauri::WindowBuilder::new(app, "main", WindowUrl::External(parsed))
                .title("OVC")
                .inner_size(1440.0, 920.0)
                .min_inner_size(1100.0, 700.0)
                .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build OVC desktop app");

    app.run(|app, event| {
            if let RunEvent::Exit = event {
                if let Ok(mut guard) = app.state::<BackendState>().child.lock() {
                    if let Some(child) = guard.as_mut() {
                        let _ = child.kill();
                    }
                    *guard = None;
                }
            }
        });
}
