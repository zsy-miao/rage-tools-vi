mod image_preview;
mod texture_preview;

use annoyed_tools::{archive::Archive, headers, index, resume, search, verify};
use iced::widget::{button, column, container, row, scrollable, text, text_input};
use iced::{Element, Length, Task};
use std::path::Path;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc,
};

const PAGE: u64 = 4096;

#[derive(Default)]
struct Explorer {
    path: String,
    offset_input: String,
    archive: Option<Archive>,
    offset: u64,
    contents: String,
    image: Option<iced::widget::image::Handle>,
    error: String,
    generation: u64,
    index_path: String,
    index_generation: u64,
    index_page: Option<index::Page>,
    index_positions: Vec<u64>,
    selected: Option<index::Range>,
    export_path: String,
    status: String,
    indexing: Option<Arc<AtomicBool>>,
    query: String,
    exporting: bool,
    export_cancel: Option<Arc<AtomicBool>>,
    export_progress: Option<Arc<AtomicU64>>,
    export_generation: u64,
    open_generation: u64,
    opening: bool,
    index_progress: Option<Arc<AtomicU64>>,
    indexing_generation: u64,
    header_mode: bool,
    header_page: Option<headers::Page>,
    header_positions: Vec<u64>,
    header_generation: u64,
    full_search: bool,
    search_cancel: Option<Arc<AtomicBool>>,
    full_query: String,
    scopes: Vec<(u64, u64)>,
    verify_cancel: Option<Arc<AtomicBool>>,
    verify_progress: Option<Arc<AtomicU64>>,
    verify_generation: u64,
    last_report: Option<(String, String, verify::Report)>,
}

#[derive(Debug, Clone)]
enum Message {
    Path(String),
    Open,
    BrowseArchive,
    ArchiveChosen(Option<std::path::PathBuf>),
    ArchiveOpened(u64, Result<Archive, String>),
    Offset(String),
    Go,
    Previous,
    Next,
    PageLoaded(u64, Result<String, String>),
    AssetLoaded(u64, Result<AssetPreview, String>),
    IndexPath(String),
    BrowseIndex,
    IndexChosen(Option<std::path::PathBuf>),
    OpenIndex,
    IndexNext,
    IndexPrevious,
    IndexSeek,
    IndexSeeked(u64, Result<u64, String>),
    ToggleHeaders,
    HeadersLoaded(u64, Result<headers::Page, String>),
    IndexLoaded(u64, Result<index::Page, String>),
    Select(index::Range),
    ExportPath(String),
    BrowseExport,
    ExportChosen(Option<std::path::PathBuf>),
    Export,
    ExportRaw,
    CancelExport,
    ExportTick(u64),
    Exported(Result<u64, String>),
    CreateIndex,
    CancelIndex,
    IndexCreated(String, Result<u64, String>),
    IndexTick(u64),
    Query(String),
    Search,
    SearchDecoded,
    CancelSearch,
    Quadrant(u8),
    ScopeUp,
    Verify,
    CompareBaseline,
    SaveBaseline,
    BaselineSaved(Result<String, String>),
    CancelVerify,
    VerifyTick(u64),
    VerifyDone(u64, String, String, bool, Result<verify::Report, String>),
}

#[derive(Debug, Clone)]
enum AssetPreview { Text(String), Image(image_preview::ImagePreview) }

fn update(state: &mut Explorer, message: Message) -> Task<Message> {
    match message {
        Message::Path(path) => state.path = path,
        Message::BrowseArchive => {
            return Task::perform(
                async {
                    rfd::FileDialog::new()
                        .add_filter("RPF archives", &["rpf"])
                        .pick_file()
                },
                Message::ArchiveChosen,
            )
        }
        Message::ArchiveChosen(Some(path)) => {
            state.path = path.to_string_lossy().into_owned();
            return update(state, Message::Open);
        }
        Message::ArchiveChosen(None) => {}
        Message::Offset(offset) => state.offset_input = offset,
        Message::Open if state.indexing.is_some() => {
            state.error = "Cancel indexing before opening another archive.".into()
        }
        Message::Open => {
            state.cancel_verify();
            state.cancel_search();
            state.full_search = false;
            let path = state.path.clone();
            state.archive = None;
            state.last_report = None;
            state.scopes.clear();
            state.selected = None;
            state.index_page = None;
            state.index_positions.clear();
            state.header_mode = false;
            state.header_page = None;
            state.header_generation = state.header_generation.wrapping_add(1);
            state.generation = state.generation.wrapping_add(1);
            state.index_generation = state.index_generation.wrapping_add(1);
            state.open_generation = state.open_generation.wrapping_add(1);
            let generation = state.open_generation;
            state.opening = true;
            state.status = "Opening…".into();
            return Task::perform(
                async move { Archive::open(Path::new(&path)).map_err(|e| e.to_string()) },
                move |result| Message::ArchiveOpened(generation, result),
            );
        }
        Message::ArchiveOpened(generation, result) if generation == state.open_generation => {
            state.opening = false;
            state.status.clear();
            match result {
                Ok(archive) => {
                    state.scopes = vec![(0, archive.size)];
                    state.archive = Some(archive);
                    state.selected = None;
                    state.offset = 0;
                    state.index_page = None;
                    state.index_positions.clear();
                    state.index_generation = state.index_generation.wrapping_add(1);
                    return state.refresh();
                }
                Err(error) => {
                    state.error = error;
                }
            }
        }
        Message::ArchiveOpened(_, _) => {}
        Message::Go => {
            let input = state.offset_input.trim();
            let parsed = if let Some(hex) = input.strip_prefix("0x") {
                u64::from_str_radix(hex, 16)
            } else {
                input.parse()
            };
            match parsed {
                Ok(offset) if state.archive.as_ref().is_some_and(|a| offset < a.size) => {
                    state.selected = None;
                    state.offset = offset;
                    return state.refresh();
                }
                _ => {
                    state.error =
                        "Offset must be within the archive (decimal or 0x hexadecimal).".into()
                }
            }
        }
        Message::Previous => {
            state.selected = None;
            state.offset = state.offset.saturating_sub(PAGE);
            return state.refresh();
        }
        Message::Next => {
            if let Some(a) = &state.archive {
                if state.offset.saturating_add(PAGE) < a.size {
                    state.selected = None;
                    state.offset += PAGE;
                    return state.refresh();
                }
            }
        }
        Message::PageLoaded(generation, result) => {
            if generation == state.generation {
                match result {
                    Ok(contents) => {
                    state.image = None;
                        state.contents = contents;
                        state.error.clear();
                    }
                    Err(error) => state.error = error,
                }
            }
        }
        Message::AssetLoaded(generation, result) if generation == state.generation => match result {
            Ok(AssetPreview::Text(text)) => { state.image = None; state.contents = text; state.error.clear(); },
            Ok(AssetPreview::Image(image)) => { state.contents = image.description; state.image = Some(iced::widget::image::Handle::from_rgba(image.width, image.height, image.rgba)); state.error.clear(); },
            Err(error) => { state.image = None; state.error = error; },
        },
        Message::AssetLoaded(_, _) => {},
        Message::IndexPath(path) => state.index_path = path,
        Message::SaveBaseline => {
            if let (Some(archive), Some((report_archive, report_index, report))) =
                (&state.archive, &state.last_report)
            {
                if archive.path.display().to_string() != *report_archive
                    || state.index_path != *report_index
                {
                    state.error =
                        "Verify the current archive and index before saving a baseline.".into();
                } else {
                    let mut path = std::ffi::OsString::from(report_index);
                    path.push(".baseline.tsv");
                    let path = std::path::PathBuf::from(path);
                    let report = report.clone();
                    return Task::perform(
                        async move {
                            report
                                .save_baseline(&path)
                                .map(|_| path.display().to_string())
                                .map_err(|e| e.to_string())
                        },
                        Message::BaselineSaved,
                    );
                }
            } else {
                state.error =
                    "Verify the current archive and index before saving a baseline.".into();
            }
        }
        Message::BaselineSaved(result) => match result {
            Ok(path) => {
                state.status = "Baseline saved.".into();
                state.image = None;
                state.contents = format!("Baseline saved to {path}\n\nKeep this file to compare future verification runs.");
                state.error.clear();
            }
            Err(error) => state.error = error,
        },
        Message::Verify | Message::CompareBaseline => {
            if state.verify_cancel.is_none() {
                if let Some(archive) = state.archive.clone() {
                    let compare = matches!(message, Message::CompareBaseline);
                    let archive_name = archive.path.display().to_string();
                    let index_name = state.index_path.clone();
                    let worker_index = index_name.clone();
                    let cancel = Arc::new(AtomicBool::new(false));
                    let progress = Arc::new(AtomicU64::new(0));
                    state.verify_cancel = Some(cancel.clone());
                    state.verify_progress = Some(progress.clone());
                    state.verify_generation = state.verify_generation.wrapping_add(1);
                    let generation = state.verify_generation;
                    state.status = "Verifying ranges…".into();
                    return Task::batch([
                        Task::perform(
                            async move {
                                let (sender, receiver) = iced::futures::channel::oneshot::channel();
                                std::thread::spawn(move || {
                                    let result = (|| {
                                        let expected = if compare {
                                            let mut baseline =
                                                std::ffi::OsString::from(&worker_index);
                                            baseline.push(".baseline.tsv");
                                            Some(verify::Baseline::read(Path::new(&baseline))?)
                                        } else {
                                            None
                                        };
                                        let report = verify::run(
                                            &archive,
                                            Path::new(&worker_index),
                                            cancel,
                                            progress,
                                        )?;
                                        if let Some(expected) = expected {
                                            expected.compare(&report)?;
                                        }
                                        Ok(report)
                                    })()
                                    .map_err(|e: std::io::Error| e.to_string());
                                    let _ = sender.send(result);
                                });
                                receiver.await.unwrap_or(Err(
                                    "Verification worker stopped unexpectedly".into(),
                                ))
                            },
                            move |result| {
                                Message::VerifyDone(
                                    generation,
                                    archive_name,
                                    index_name,
                                    compare,
                                    result,
                                )
                            },
                        ),
                        verify_tick(generation),
                    ]);
                }
            }
        }
        Message::CancelVerify => state.cancel_verify(),
        Message::VerifyTick(generation) if generation == state.verify_generation => {
            if let (Some(progress), Some(archive), Some(cancel)) =
                (&state.verify_progress, &state.archive, &state.verify_cancel)
            {
                if !cancel.load(Ordering::Relaxed) {
                    let done = progress.load(Ordering::Relaxed);
                    state.status = if done >= archive.size {
                        "Hashing source and index…".into()
                    } else {
                        format!("Checking {:.1}%", 100.0 * done as f64 / archive.size as f64)
                    };
                }
                return verify_tick(generation);
            }
        }
        Message::VerifyTick(_) => {}
        Message::VerifyDone(generation, archive_name, index_name, compared, result)
            if generation == state.verify_generation =>
        {
            state.verify_cancel = None;
            state.verify_progress = None;
            match result {
                Ok(report) => {
                    state.generation = state.generation.wrapping_add(1);
                    state.image = None;
                    state.status = if compared {
                        "Baseline matches."
                    } else {
                        "Verification complete."
                    }
                    .into();
                    state.error.clear();
                    state.last_report =
                        Some((archive_name.clone(), index_name.clone(), report.clone()));
                    state.contents = format!("Coverage and zlib checks passed.\n\nArchive: {archive_name}\nIndex: {index_name}\nRanges: {}\nZlib streams: {}\nRaw DEFLATE streams: {} (no checksum)\nUnclassified bytes: {}\nBytes without zlib/zero content checks: {}\nArchive SHA-256: {}\nIndex SHA-256: {}\n\nHashes are baselines; they do not decode or prove archive entries.", report.ranges, report.zlib_streams, report.raw_deflate_streams, report.unclassified_bytes, report.unchecked_bytes, report.archive_sha256, report.index_sha256);
                }
                Err(error) => {
                    state.status.clear();
                    state.error = error;
                }
            }
        }
        Message::VerifyDone(_, _, _, _, _) => {}
        Message::ToggleHeaders => {
            state.cancel_search();
            state.header_mode = !state.header_mode;
            state.scopes.truncate(1);
            state.selected = None;
            if state.header_mode {
                state.header_positions = vec![0];
                return state.load_headers(0);
            } else if state.index_page.is_some() {
                state.full_search = false;
                state.index_positions = vec![0];
                return state.load_index(0);
            }
        }
        Message::HeadersLoaded(generation, result) if generation == state.header_generation => {
            match result {
                Ok(page) => {
                    state.header_page = Some(page);
                    state.error.clear();
                }
                Err(error) => {
                    state.header_page = None;
                    state.error = error;
                }
            }
        }
        Message::HeadersLoaded(_, _) => {}
        Message::IndexSeek => {
            state.cancel_search();
            state.full_search = false;
            state.scopes.truncate(1);
            return state.seek_index(state.offset);
        }
        Message::Quadrant(quadrant) => {
            if let Some(&(start, end)) = state.scopes.last() {
                let size = end - start;
                if size < 4 {
                    return Task::none();
                }
                let part = size / 4;
                let remainder = size % 4;
                let boundary = |i: u64| start + part * i + remainder.min(i);
                let a = boundary(quadrant as u64);
                let b = boundary(quadrant as u64 + 1);
                state.cancel_search();
                state.full_search = false;
                state.header_mode = false;
                state.scopes.push((a, b));
                return state.seek_index(a);
            }
        }
        Message::ScopeUp => {
            if state.scopes.len() > 1 {
                state.cancel_search();
                state.full_search = false;
                state.scopes.pop();
                return state.seek_index(state.scopes.last().unwrap().0);
            }
        }
        Message::IndexSeeked(generation, result) if generation == state.index_generation => {
            match result {
                Ok(position) => {
                    state.index_positions = vec![position];
                    return state.load_index(position);
                }
                Err(error) => state.error = error,
            }
        }
        Message::IndexSeeked(_, _) => {}
        Message::BrowseIndex => {
            return Task::perform(
                async {
                    rfd::FileDialog::new()
                        .add_filter("Stream index", &["tsv"])
                        .pick_file()
                },
                Message::IndexChosen,
            )
        }
        Message::IndexChosen(Some(path)) => state.index_path = path.to_string_lossy().into_owned(),
        Message::IndexChosen(None) => {}
        Message::Query(query) => state.query = query,
        Message::Search => {
            state.cancel_search();
            state.full_search = false;
            state.scopes.truncate(1);
            state.selected = None;
            state.index_positions = vec![0];
            return state.load_index(0);
        }
        Message::SearchDecoded => {
            state.cancel_search();
            state.full_search = true;
            state.scopes.truncate(1);
            state.full_query = state.query.clone();
            state.header_mode = false;
            state.selected = None;
            state.index_positions = vec![0];
            return state.load_full_search(0);
        }
        Message::CancelSearch => state.cancel_search(),
        Message::CreateIndex => {
            if state.indexing.is_none() && !state.opening {
                if let Some(archive) = state.archive.clone() {
                    let path = state.index_path.clone();
                    let cancel = Arc::new(AtomicBool::new(false));
                    let progress = Arc::new(AtomicU64::new(0));
                    state.index_progress = Some(progress.clone());
                    state.indexing_generation = state.indexing_generation.wrapping_add(1);
                    let generation = state.indexing_generation;
                    state.indexing = Some(cancel.clone());
                    state.status = "Indexing…".into();
                    return Task::batch([
                        Task::perform(
                            async move {
                                let (sender, receiver) = iced::futures::channel::oneshot::channel();
                                let failure_path = path.clone();
                                std::thread::spawn(move || {
                                    let result = resume::create(
                                        &archive,
                                        Path::new(&path),
                                        cancel,
                                        progress,
                                    )
                                    .map_err(|e| e.to_string());
                                    let _ = sender.send((path, result));
                                });
                                receiver.await.unwrap_or((
                                    failure_path,
                                    Err("Index worker stopped unexpectedly".into()),
                                ))
                            },
                            |(path, result)| Message::IndexCreated(path, result),
                        ),
                        tick(generation),
                    ]);
                }
            }
        }
        Message::CancelIndex => {
            if let Some(cancel) = &state.indexing {
                cancel.store(true, Ordering::Relaxed);
                state.status = "Pausing…".into();
            }
        }
        Message::IndexTick(generation) if generation == state.indexing_generation => {
            if let (Some(progress), Some(archive), Some(cancel)) =
                (&state.index_progress, &state.archive, &state.indexing)
            {
                if !cancel.load(Ordering::Relaxed) {
                    state.status = format!(
                        "Indexing {:.1}%",
                        100.0 * progress.load(Ordering::Relaxed) as f64 / archive.size as f64
                    );
                }
                return tick(generation);
            }
        }
        Message::IndexTick(_) => {}
        Message::IndexCreated(path, result) => {
            state.indexing = None;
            state.index_progress = None;
            match result {
                Ok(count) => {
                    state.cancel_search();
                    state.full_search = false;
                    state.status = format!("Indexed {count} streams.");
                    state.index_path = path;
                    state.index_positions = vec![0];
                    return state.load_index(0);
                }
                Err(error) => {
                    if error.starts_with("Indexing paused;") {
                        state.status = "Paused; resume with the same destination.".into();
                        state.error.clear();
                    } else {
                        state.status.clear();
                        state.error = error;
                    }
                }
            }
        }
        Message::OpenIndex => {
            state.cancel_search();
            state.full_search = false;
            state.scopes.truncate(1);
            state.selected = None;
            state.index_positions = vec![0];
            return state.load_index(0);
        }
        Message::IndexNext => {
            if state.header_mode {
                if let Some(next) = state.header_page.as_ref().and_then(|page| page.next) {
                    state.header_positions.push(next);
                    return state.load_headers(next);
                }
                return Task::none();
            }
            if let Some(next) = state.index_page.as_ref().and_then(|page| page.next) {
                state.index_positions.push(next);
                return if state.full_search {
                    state.load_full_search(next)
                } else {
                    state.load_index(next)
                };
            }
        }
        Message::IndexPrevious => {
            if state.header_mode {
                if state.header_positions.len() > 1 {
                    state.header_positions.pop();
                    return state.load_headers(*state.header_positions.last().unwrap());
                }
                return Task::none();
            }
            if state.index_positions.len() > 1 {
                state.index_positions.pop();
                let position = *state.index_positions.last().unwrap();
                return if state.full_search {
                    state.load_full_search(position)
                } else {
                    state.load_index(position)
                };
            }
        }
        Message::IndexLoaded(generation, result) => {
            if generation == state.index_generation {
                if state.full_search {
                    state.search_cancel = None;
                    state.status.clear();
                }
                match result {
                    Ok(page) => {
                        state.index_page = Some(page);
                        state.error.clear();
                    }
                    Err(error) => {
                        state.index_page = None;
                        state.error = error;
                    }
                }
            }
        }
        Message::Select(range) => {
            if state.archive.as_ref().is_some_and(|a| range.end <= a.size) {
                state.offset = range.start;
                state.selected = Some(range.clone());
                if range.kind == "zlib" || range.kind == "raw_deflate" {
                    let archive = state.archive.clone().unwrap();
                    let index_path = state.index_path.clone();
                    state.generation = state.generation.wrapping_add(1);
                    let generation = state.generation;
                    state.offset_input = format!("0x{:x}", range.start);
                    state.contents = "Decoding preview…".into();
                    state.image = None;
                    return Task::perform(
                        async move {
                            (|| {
                                let raw = range.kind == "raw_deflate";
                                if let Some(image) = image_preview::load(&archive, range.start, range.end, raw)? { return Ok(AssetPreview::Image(image)); }
                                if !raw {
                                    if let Some(image) = texture_preview::load(&archive, Path::new(&index_path), &range)? { return Ok(AssetPreview::Image(image)); }
                                }
                                let text = if raw { archive.preview_deflate(range.start, range.end)? } else { archive.preview_zlib(range.start, range.end)? };
                                Ok(AssetPreview::Text(text))
                            })().map_err(|e: std::io::Error| e.to_string())
                        },
                        move |result| Message::AssetLoaded(generation, result),
                    );
                }
                return state.refresh();
            } else {
                state.error = "Range is outside the open archive.".into();
            }
        }
        Message::ExportPath(path) => state.export_path = path,
        Message::BrowseExport => {
            return Task::perform(
                async { rfd::FileDialog::new().save_file() },
                Message::ExportChosen,
            )
        }
        Message::ExportChosen(Some(path)) => {
            state.export_path = path.to_string_lossy().into_owned()
        }
        Message::ExportChosen(None) => {}
        Message::Export | Message::ExportRaw if state.exporting => {}
        Message::Export | Message::ExportRaw => {
            if let (Some(archive), Some(range)) = (state.archive.clone(), state.selected.clone()) {
                let raw = matches!(message, Message::ExportRaw);
                if !raw && range.kind != "zlib" && range.kind != "raw_deflate" {
                    state.error = "Select a zlib or raw DEFLATE range for decoded export.".into();
                } else {
                    let path = state.export_path.clone();
                    state.exporting = true;
                    let cancel = Arc::new(AtomicBool::new(false));
                    let progress = Arc::new(AtomicU64::new(0));
                    state.export_cancel = Some(cancel.clone());
                    state.export_progress = Some(progress.clone());
                    state.export_generation = state.export_generation.wrapping_add(1);
                    let generation = state.export_generation;
                    state.status = "Exporting…".into();
                    return Task::batch([
                        Task::perform(
                            async move {
                                let (sender, receiver) = iced::futures::channel::oneshot::channel();
                                std::thread::spawn(move || {
                                    let result = if raw {
                                        archive.export_raw_cancellable(
                                            range.start,
                                            range.end,
                                            Path::new(&path),
                                            &cancel,
                                            &progress,
                                        )
                                    } else if range.kind == "raw_deflate" {
                                        archive.export_deflate_cancellable(
                                            range.start,
                                            range.end,
                                            Path::new(&path),
                                            &cancel,
                                            &progress,
                                        )
                                    } else {
                                        archive.export_zlib_cancellable(
                                            range.start,
                                            range.end,
                                            Path::new(&path),
                                            &cancel,
                                            &progress,
                                        )
                                    }
                                    .map_err(|e| e.to_string());
                                    let _ = sender.send(result);
                                });
                                receiver
                                    .await
                                    .unwrap_or(Err("Export worker stopped unexpectedly".into()))
                            },
                            Message::Exported,
                        ),
                        export_tick(generation),
                    ]);
                }
            } else {
                state.error = "Select a range first.".into();
            }
        }
        Message::CancelExport => {
            if let Some(cancel) = &state.export_cancel {
                cancel.store(true, Ordering::Relaxed);
                state.status = "Cancelling export…".into();
            }
        }
        Message::ExportTick(generation) if generation == state.export_generation => {
            if let (Some(progress), Some(cancel)) = (&state.export_progress, &state.export_cancel) {
                if !cancel.load(Ordering::Relaxed) {
                    state.status = format!("Exported {} bytes…", progress.load(Ordering::Relaxed));
                }
                return export_tick(generation);
            }
        }
        Message::ExportTick(_) => {}
        Message::Exported(result) => {
            state.exporting = false;
            state.export_cancel = None;
            state.export_progress = None;
            match result {
                Ok(bytes) => {
                    state.status = format!("Exported {bytes} bytes.");
                    state.error.clear();
                }
                Err(error) => {
                    if error.starts_with("Export cancelled") {
                        state.status = "Export cancelled.".into();
                        state.error.clear();
                    } else {
                        state.status.clear();
                        state.error = error;
                    }
                }
            }
        }
    }
    Task::none()
}

fn tick(generation: u64) -> Task<Message> {
    Task::perform(
        async {
            let (sender, receiver) = iced::futures::channel::oneshot::channel();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(250));
                let _ = sender.send(());
            });
            let _ = receiver.await;
        },
        move |_| Message::IndexTick(generation),
    )
}

fn export_tick(generation: u64) -> Task<Message> {
    Task::perform(
        async {
            let (sender, receiver) = iced::futures::channel::oneshot::channel();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(250));
                let _ = sender.send(());
            });
            let _ = receiver.await;
        },
        move |_| Message::ExportTick(generation),
    )
}

fn verify_tick(generation: u64) -> Task<Message> {
    Task::perform(
        async {
            let (sender, receiver) = iced::futures::channel::oneshot::channel();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(250));
                let _ = sender.send(());
            });
            let _ = receiver.await;
        },
        move |_| Message::VerifyTick(generation),
    )
}

impl Explorer {
    fn cancel_verify(&mut self) {
        if let Some(cancel) = self.verify_cancel.take() {
            cancel.store(true, Ordering::Relaxed);
            self.verify_progress = None;
            self.verify_generation = self.verify_generation.wrapping_add(1);
            self.status = "Verification cancelled.".into();
        }
    }
    fn cancel_search(&mut self) {
        if let Some(cancel) = self.search_cancel.take() {
            cancel.store(true, Ordering::Relaxed);
            self.index_generation = self.index_generation.wrapping_add(1);
            self.status = "Search cancelled.".into();
        }
    }

    fn load_full_search(&mut self, position: u64) -> Task<Message> {
        let Some(archive) = self.archive.clone() else {
            return Task::none();
        };
        let path = self.index_path.clone();
        let query = self.full_query.clone();
        let cancel = Arc::new(AtomicBool::new(false));
        self.search_cancel = Some(cancel.clone());
        self.index_generation = self.index_generation.wrapping_add(1);
        let generation = self.index_generation;
        self.index_page = None;
        self.status = "Searching decoded content…".into();
        Task::perform(
            async move {
                let (sender, receiver) = iced::futures::channel::oneshot::channel();
                std::thread::spawn(move || {
                    let result = search::page(
                        &archive,
                        Path::new(&path),
                        position,
                        query.as_bytes(),
                        cancel,
                    )
                    .map_err(|e| e.to_string());
                    let _ = sender.send(result);
                });
                receiver
                    .await
                    .unwrap_or(Err("Search worker stopped unexpectedly".into()))
            },
            move |result| Message::IndexLoaded(generation, result),
        )
    }

    fn load_headers(&mut self, position: u64) -> Task<Message> {
        let Some(archive) = self.archive.clone() else {
            return Task::none();
        };
        self.header_generation = self.header_generation.wrapping_add(1);
        let generation = self.header_generation;
        self.header_page = None;
        Task::perform(
            async move { headers::scan(&archive, position).map_err(|e| e.to_string()) },
            move |result| Message::HeadersLoaded(generation, result),
        )
    }
    fn seek_index(&mut self, offset: u64) -> Task<Message> {
        let path = self.index_path.clone();
        let size = self.archive.as_ref().map(|archive| archive.size);
        self.index_generation = self.index_generation.wrapping_add(1);
        let generation = self.index_generation;
        self.query.clear();
        self.index_page = None;
        Task::perform(
            async move {
                (|| {
                    let path = Path::new(&path);
                    if let Some(size) = size {
                        index::check_archive_size(path, size)?;
                    }
                    index::seek_offset(path, offset)
                })()
                .map_err(|error: std::io::Error| error.to_string())
            },
            move |result| Message::IndexSeeked(generation, result),
        )
    }
    fn load_index(&mut self, position: u64) -> Task<Message> {
        self.index_generation = self.index_generation.wrapping_add(1);
        let generation = self.index_generation;
        let path = self.index_path.clone();
        let query = self.query.clone();
        let archive_size = self.archive.as_ref().map(|a| a.size);
        let scope_end = if self.scopes.len() > 1 {
            self.scopes.last().map(|scope| scope.1)
        } else {
            None
        };
        self.index_page = None;
        Task::perform(
            async move {
                (|| {
                    let path = Path::new(&path);
                    if let Some(size) = archive_size {
                        index::check_archive_size(path, size)?;
                    }
                    index::page_until(path, position, &query, scope_end)
                })()
                .map_err(|e: std::io::Error| e.to_string())
            },
            move |result| Message::IndexLoaded(generation, result),
        )
    }
    fn refresh(&mut self) -> Task<Message> {
        let Some(archive) = self.archive.clone() else {
            return Task::none();
        };
        self.generation = self.generation.wrapping_add(1);
        let generation = self.generation;
        let offset = self.offset;
        self.offset_input = format!("0x{offset:x}");
        self.contents = "Loading…".into();
        self.image = None;
        Task::perform(
            async move {
                archive
                    .read(offset, PAGE as usize)
                    .map(|bytes| {
                        bytes
                            .chunks(16)
                            .enumerate()
                            .map(|(i, chunk)| {
                                let hex = chunk
                                    .iter()
                                    .map(|b| format!("{b:02x} "))
                                    .collect::<String>();
                                let ascii: String = chunk
                                    .iter()
                                    .map(|&b| {
                                        if (32..127).contains(&b) {
                                            b as char
                                        } else {
                                            '.'
                                        }
                                    })
                                    .collect();
                                format!(
                                    "{:016x}  {:48}  {}\n",
                                    offset + (i * 16) as u64,
                                    hex,
                                    ascii
                                )
                            })
                            .collect()
                    })
                    .map_err(|error| error.to_string())
            },
            move |result| Message::PageLoaded(generation, result),
        )
    }
}

fn view(state: &Explorer) -> Element<'_, Message> {
    let open = row![
        text_input("Path to RPF9 archive", &state.path)
            .on_input(Message::Path)
            .on_submit(Message::Open),
        button("Browse…").on_press(Message::BrowseArchive),
        button("Open").on_press(Message::Open),
        button("Verify index").on_press(Message::Verify),
        button("Stop verify").on_press(Message::CancelVerify),
        button("Save baseline").on_press(Message::SaveBaseline),
        button("Compare baseline").on_press(Message::CompareBaseline)
    ]
    .spacing(8);
    let mut content = column![text("Annoyed Tools").size(28), open].spacing(12);
    if !state.error.is_empty() {
        content = content.push(text(&state.error));
    }
    if let Some(a) = &state.archive {
        content = content.push(text(format!(
            "{} bytes  ·  front end 0x{:x}  ·  trailer {} bytes  ·  header count {}",
            a.size,
            a.word(4),
            a.word(12),
            a.word(0x24)
        )));
        content = content.push(
            row![
                button("Previous 4 KiB").on_press(Message::Previous),
                text_input("Offset", &state.offset_input)
                    .on_input(Message::Offset)
                    .on_submit(Message::Go)
                    .width(200),
                button("Go").on_press(Message::Go),
                button("Next 4 KiB").on_press(Message::Next)
            ]
            .spacing(8),
        );
        content = content.push(text("Offsets are archive-relative; end exclusive. Index must belong to this archive; ranges are not decoded entry records.").size(14));
        content = content.push(
            row![
                text_input("Export selected range to new file", &state.export_path)
                    .on_input(Message::ExportPath)
                    .width(Length::Fill),
                button("Browse…").on_press(Message::BrowseExport),
                button("Export raw").on_press(Message::ExportRaw),
                button("Export decoded").on_press(Message::Export),
                button("Stop export").on_press(Message::CancelExport),
                text(&state.status)
            ]
            .spacing(6),
        );
        let mut ranges = column![
            text(if state.header_mode {
                "RPF9 header candidates"
            } else {
                "Carved ranges (stream index)"
            })
            .size(17),
            row![
                text_input("Path to index TSV", &state.index_path)
                    .on_input(Message::IndexPath)
                    .on_submit(Message::OpenIndex),
                button("Browse…").on_press(Message::BrowseIndex),
                button("Load").on_press(Message::OpenIndex)
            ]
            .spacing(4),
            row![
                button("Index / Resume").on_press(Message::CreateIndex),
                button("Pause").on_press(Message::CancelIndex).width(140),
                button("Full search").on_press(Message::SearchDecoded),
                button("Stop").on_press(Message::CancelSearch)
            ]
            .spacing(4),
            row![
                text_input("Filter kind, offset or text prefix", &state.query)
                    .on_input(Message::Query)
                    .on_submit(Message::Search),
                button("Search").on_press(Message::Search)
            ]
            .spacing(4),
            row![
                button("Previous").on_press(Message::IndexPrevious),
                button("Next").on_press(Message::IndexNext),
                button("Find offset").on_press(Message::IndexSeek),
                button(if state.header_mode {
                    "Ranges"
                } else {
                    "Headers"
                })
                .on_press(Message::ToggleHeaders)
            ]
            .spacing(4),
            row![
                button("Q1").on_press(Message::Quadrant(0)),
                button("Q2").on_press(Message::Quadrant(1)),
                button("Q3").on_press(Message::Quadrant(2)),
                button("Q4").on_press(Message::Quadrant(3)),
                button("Up").on_press(Message::ScopeUp)
            ]
            .spacing(4)
        ]
        .spacing(6);
        if state.scopes.len() > 1 {
            let (start, end) = state.scopes.last().copied().unwrap();
            ranges = ranges.push(
                text(format!(
                    "Byte slice 0x{start:x}–0x{end:x}; ranges may cross boundaries."
                ))
                .size(12),
            );
        }
        let mut entries = column![].spacing(6);
        if state.full_search && !state.header_mode {
            entries = entries
                .push(text("Full decoded search is case-sensitive; Next scans further.").size(12));
        }
        if !state.header_mode
            && state
                .index_page
                .as_ref()
                .is_some_and(|page| page.rows.is_empty() && page.next.is_some())
        {
            entries = entries
                .push(text("No matches in this batch; use Next to search further.").size(12));
        }
        if state.header_mode {
            if let Some(page) = &state.header_page {
                entries = entries.push(
                    text("Plausible headers only; pack bounds are not established.").size(12),
                );
                if page.headers.is_empty() && page.next.is_some() {
                    entries =
                        entries.push(text("No headers in this 64 MiB batch; use Next.").size(12));
                }
                for header in &page.headers {
                    let range = index::Range {
                        kind: "RPF9 candidate".into(),
                        start: header.offset,
                        end: header.offset + 96,
                        decoded: String::new(),
                        text_prefix: String::new(),
                    };
                    entries = entries.push(
                        button(
                            text(format!(
                                "0x{:x} · front 0x{:x} · trailer {} · declared {}",
                                header.offset,
                                header.front_bytes,
                                header.trailer_bytes,
                                header.declared_entries
                            ))
                            .size(12),
                        )
                        .on_press(Message::Select(range)),
                    );
                }
            } else {
                entries =
                    entries.push(text("Scanning up to 64 MiB for header candidates…").size(12));
            }
        } else if let Some(page) = &state.index_page {
            for range in &page.rows {
                let label = if range.text_prefix.is_empty() {
                    String::new()
                } else {
                    let prefix = &range.text_prefix;
                    let name = prefix
                        .split_once("<id>")
                        .and_then(|(_, rest)| rest.split_once("</id>").map(|(name, _)| name))
                        .unwrap_or(prefix);
                    format!("\n{}", name.chars().take(50).collect::<String>())
                };
                entries = entries.push(
                    button(
                        text(format!(
                            "{}  0x{:x}–0x{:x}  {} decoded{}",
                            range.kind, range.start, range.end, range.decoded, label
                        ))
                        .size(12),
                    )
                    .on_press(Message::Select(range.clone())),
                );
            }
        }
        ranges = ranges.push(scrollable(entries).height(Length::Fill));
        let preview: Element<'_, Message> = if let Some(handle) = &state.image {
            column![text(&state.contents).size(14), iced::widget::image(handle.clone()).content_fit(iced::ContentFit::Contain).width(Length::Fill).height(Length::Fill)].spacing(8).into()
        } else {
            scrollable(text(&state.contents).font(iced::Font::MONOSPACE).size(12)).height(Length::Fill).into()
        };
        content = content.push(
            row![
                ranges.width(Length::FillPortion(2)).height(Length::Fill),
                container(preview).width(Length::FillPortion(3)).height(Length::Fill)
            ]
            .spacing(12)
            .height(Length::Fill),
        );
    }
    container(content)
        .padding(20)
        .width(Length::Fill)
        .height(Length::Fill)
        .into()
}

fn main() -> iced::Result {
    iced::application(Explorer::default, update, view)
        .title("Annoyed Tools")
        .run()
}
