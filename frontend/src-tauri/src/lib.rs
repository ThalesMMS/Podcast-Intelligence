use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Mutex,
    },
    time::Duration,
};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use uuid::Uuid;

const ENGINE_SIDECAR: &str = "podcast-intelligence-engine";
const STARTUP_ATTEMPTS: usize = 450;
const STARTUP_INTERVAL_MS: u64 = 200;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeConfig {
    status: String,
    api_base_url: String,
    api_token: Option<String>,
    mcp_url: Option<String>,
    data_dir: Option<String>,
    error: Option<String>,
}

impl RuntimeConfig {
    fn starting(data_dir: &Path) -> Self {
        Self {
            status: "starting".into(),
            api_base_url: String::new(),
            api_token: None,
            mcp_url: None,
            data_dir: Some(data_dir.to_string_lossy().into_owned()),
            error: None,
        }
    }
}

struct EngineManager {
    runtime: Mutex<RuntimeConfig>,
    child: Mutex<Option<CommandChild>>,
    data_dir: PathBuf,
    generation: AtomicU64,
    expected_shutdown: AtomicBool,
}

impl EngineManager {
    fn new(data_dir: PathBuf) -> Self {
        Self {
            runtime: Mutex::new(RuntimeConfig::starting(&data_dir)),
            child: Mutex::new(None),
            data_dir,
            generation: AtomicU64::new(0),
            expected_shutdown: AtomicBool::new(false),
        }
    }

    fn set_failed(&self, message: impl Into<String>) {
        let mut runtime = self.runtime.lock().expect("engine runtime mutex poisoned");
        runtime.status = "failed".into();
        runtime.error = Some(message.into());
    }
}

#[derive(Debug, Deserialize)]
struct EngineEvent {
    event: String,
    api_url: Option<String>,
    mcp_url: Option<String>,
    data_dir: Option<String>,
    message: Option<String>,
    error_type: Option<String>,
}

#[tauri::command]
fn runtime_config(state: State<'_, EngineManager>) -> RuntimeConfig {
    state
        .runtime
        .lock()
        .expect("engine runtime mutex poisoned")
        .clone()
}

#[tauri::command]
fn read_desktop_settings(state: State<'_, EngineManager>) -> Result<Value, String> {
    let path = state.data_dir.join("settings.json");
    if !path.exists() {
        return Ok(serde_json::json!({
            "ai_profile": "demo",
            "transcription_provider": "demo",
            "embedding_provider": "demo",
            "llm_provider": "demo",
            "openai_llm_api": "chat_completions",
            "openai_transcription_model": "gpt-4o-transcribe-diarize",
            "openai_embedding_model": "text-embedding-3-small",
            "openai_llm_model": "gpt-5.6-luna",
            "embedding_dimension": 1536,
            "openai_embedding_send_dimensions": false,
            "desktop_job_workers": 2
        }));
    }
    let contents = fs::read_to_string(&path).map_err(|error| error.to_string())?;
    serde_json::from_str(&contents).map_err(|error| error.to_string())
}

#[tauri::command]
fn write_desktop_settings(
    state: State<'_, EngineManager>,
    settings: Value,
) -> Result<(), String> {
    if !settings.is_object() {
        return Err("Settings must be a JSON object".into());
    }
    fs::create_dir_all(&state.data_dir).map_err(|error| error.to_string())?;
    let path = state.data_dir.join("settings.json");
    let temporary = state.data_dir.join("settings.json.tmp");
    let encoded = serde_json::to_vec_pretty(&settings).map_err(|error| error.to_string())?;
    fs::write(&temporary, encoded).map_err(|error| error.to_string())?;
    restrict_file_permissions(&temporary)?;
    replace_file(&temporary, &path)?;
    restrict_file_permissions(&path)?;
    Ok(())
}

#[tauri::command]
fn write_export_file(path: String, contents: String) -> Result<(), String> {
    let destination = PathBuf::from(path);
    if !destination.is_absolute() {
        return Err("Export destination must be an absolute path".to_string());
    }
    let extension = destination
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !matches!(extension.as_str(), "md" | "json" | "srt" | "vtt") {
        return Err("Unsupported export extension".to_string());
    }
    fs::write(destination, contents).map_err(|error| error.to_string())
}

#[tauri::command]
async fn restart_engine(app: AppHandle, state: State<'_, EngineManager>) -> Result<(), String> {
    stop_engine(&state).await;
    launch_engine(&app, &state)
}


fn replace_file(source: &Path, destination: &Path) -> Result<(), String> {
    #[cfg(windows)]
    if destination.exists() {
        fs::remove_file(destination).map_err(|error| error.to_string())?;
    }
    fs::rename(source, destination).map_err(|error| error.to_string())
}

fn restrict_file_permissions(path: &Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let permissions = fs::Permissions::from_mode(0o600);
        fs::set_permissions(path, permissions).map_err(|error| error.to_string())?;
    }
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

fn launch_engine(app: &AppHandle, state: &EngineManager) -> Result<(), String> {
    let generation = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    state.expected_shutdown.store(false, Ordering::SeqCst);
    {
        let mut runtime = state.runtime.lock().map_err(|error| error.to_string())?;
        *runtime = RuntimeConfig::starting(&state.data_dir);
    }

    let api_token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    let arguments = vec![
        "--data-dir".to_string(),
        state.data_dir.to_string_lossy().into_owned(),
        "--api-token".to_string(),
        api_token.clone(),
        "--port".to_string(),
        "0".to_string(),
        "--mcp-port".to_string(),
        "8001".to_string(),
    ];

    let command = app
        .shell()
        .sidecar(ENGINE_SIDECAR)
        .map_err(|error| format!("Could not resolve desktop engine sidecar: {error}"))?
        .args(arguments);
    let (mut receiver, child) = command
        .spawn()
        .map_err(|error| format!("Could not launch desktop engine: {error}"))?;
    {
        let mut stored = state.child.lock().map_err(|error| error.to_string())?;
        *stored = Some(child);
    }

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            let manager = handle.state::<EngineManager>();
            if manager.generation.load(Ordering::SeqCst) != generation {
                continue;
            }
            match event {
                CommandEvent::Stdout(bytes) => {
                    let line = String::from_utf8_lossy(&bytes);
                    if let Ok(parsed) = serde_json::from_str::<EngineEvent>(&line) {
                        match parsed.event.as_str() {
                            "listening" => {
                                let Some(api_url) = parsed.api_url else {
                                    manager.set_failed("Engine did not report its API address");
                                    continue;
                                };
                                {
                                    let mut runtime = manager
                                        .runtime
                                        .lock()
                                        .expect("engine runtime mutex poisoned");
                                    runtime.api_base_url = api_url.clone();
                                    runtime.api_token = Some(api_token.clone());
                                    runtime.mcp_url = parsed.mcp_url;
                                    runtime.data_dir = parsed.data_dir;
                                    runtime.error = None;
                                }
                                let health_handle = handle.clone();
                                let health_token = api_token.clone();
                                tauri::async_runtime::spawn(async move {
                                    wait_for_engine(
                                        health_handle,
                                        generation,
                                        api_url,
                                        health_token,
                                    )
                                    .await;
                                });
                            }
                            "fatal" => {
                                let kind = parsed.error_type.unwrap_or_else(|| "EngineError".into());
                                manager.set_failed(format!(
                                    "{kind}: {}",
                                    parsed.message.unwrap_or_else(|| "Unknown engine error".into())
                                ));
                            }
                            _ => {}
                        }
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    eprintln!("[podcast-engine] {}", String::from_utf8_lossy(&bytes));
                }
                CommandEvent::Error(error) => manager.set_failed(error),
                CommandEvent::Terminated(payload) => {
                    if !manager.expected_shutdown.load(Ordering::SeqCst) {
                        let status = manager
                            .runtime
                            .lock()
                            .expect("engine runtime mutex poisoned")
                            .status
                            .clone();
                        if status != "failed" {
                            manager.set_failed(format!(
                                "Local engine exited unexpectedly (code {:?}, signal {:?})",
                                payload.code, payload.signal
                            ));
                        }
                    }
                }
                _ => {}
            }
        }
    });
    Ok(())
}

async fn wait_for_engine(
    app: AppHandle,
    generation: u64,
    api_url: String,
    _api_token: String,
) {
    let client = match reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(2))
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(client) => client,
        Err(error) => {
            app.state::<EngineManager>()
                .set_failed(format!("Could not create health-check client: {error}"));
            return;
        }
    };
    for _ in 0..STARTUP_ATTEMPTS {
        let manager = app.state::<EngineManager>();
        if manager.generation.load(Ordering::SeqCst) != generation {
            return;
        }
        if let Ok(response) = client.get(format!("{api_url}/health/ready")).send().await {
            if response.status().is_success() {
                let mut runtime = manager
                    .runtime
                    .lock()
                    .expect("engine runtime mutex poisoned");
                runtime.status = "ready".into();
                runtime.error = None;
                return;
            }
        }
        tokio_sleep(Duration::from_millis(STARTUP_INTERVAL_MS)).await;
    }
    app.state::<EngineManager>()
        .set_failed("Local engine did not become ready within 90 seconds");
}

async fn tokio_sleep(duration: Duration) {
    tokio::time::sleep(duration).await;
}

async fn stop_engine(state: &EngineManager) {
    state.expected_shutdown.store(true, Ordering::SeqCst);
    let runtime = state
        .runtime
        .lock()
        .expect("engine runtime mutex poisoned")
        .clone();
    if !runtime.api_base_url.is_empty() {
        let mut request = reqwest::Client::new()
            .post(format!("{}/v1/desktop/shutdown", runtime.api_base_url));
        if let Some(token) = runtime.api_token {
            request = request.header("X-Desktop-Token", token);
        }
        let _ = request.timeout(Duration::from_secs(2)).send().await;
        tokio_sleep(Duration::from_millis(750)).await;
    }
    let child = state
        .child
        .lock()
        .expect("engine child mutex poisoned")
        .take();
    if let Some(child) = child {
        let _ = child.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            fs::create_dir_all(&data_dir)?;
            app.manage(EngineManager::new(data_dir));
            let state = app.state::<EngineManager>();
            launch_engine(app.handle(), &state).map_err(|error| {
                std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Could not start local engine: {error}"),
                )
            })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            runtime_config,
            read_desktop_settings,
            write_desktop_settings,
            write_export_file,
            restart_engine
        ])
        .build(tauri::generate_context!())
        .expect("error while building Podcast Intelligence");

    app.run(|handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            let state = handle.state::<EngineManager>();
            tauri::async_runtime::block_on(stop_engine(&state));
        }
    });
}
