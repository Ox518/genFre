use crate::{
    config::Config,
    db::{self, DbPool, ShareRow},
    jobs::JobManager,
    protocol::*,
    shares,
    vardiff::VarDiffManager,
};
use anyhow::Result;
use chrono::Utc;
use rand::Rng;
use serde_json::{json, Value};
use std::sync::Arc;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{TcpListener, TcpStream},
    sync::mpsc,
};

// ── Shared server state ──────────────────────────────────────────────────────

struct Shared {
    db:      DbPool,
    jobs:    Arc<JobManager>,
    vardiff: Arc<VarDiffManager>,
    cfg:     Config,
}

// ── Listener ─────────────────────────────────────────────────────────────────

pub async fn run(
    cfg:     Config,
    db:      DbPool,
    jobs:    Arc<JobManager>,
    vardiff: Arc<VarDiffManager>,
) -> Result<()> {
    let listener = TcpListener::bind(&cfg.listen_addr).await?;
    tracing::info!("listening on {}", cfg.listen_addr);

    let shared = Arc::new(Shared { db, jobs, vardiff, cfg });

    loop {
        let (socket, addr) = listener.accept().await?;
        tracing::debug!("connect: {}", addr);
        let s = shared.clone();
        tokio::spawn(async move {
            if let Err(e) = handle(socket, addr.to_string(), s).await {
                tracing::warn!("[{}] disconnected: {:?}", addr, e);
            }
        });
    }
}

// ── Per-client state machine ──────────────────────────────────────────────────

#[derive(Default)]
struct Session {
    extranonce1:      Option<String>,
    extranonce2_size: u8,
    worker_name:      Option<String>,
    coin:             Option<String>,
    subscribed:       bool,
    authorized:       bool,
}

async fn handle(stream: TcpStream, addr: String, shared: Arc<Shared>) -> Result<()> {
    let (r, mut w) = stream.into_split();
    let mut reader  = BufReader::new(r);
    let mut line    = String::new();
    let mut sess    = Session::default();
    sess.extranonce2_size = shared.cfg.pool.extranonce2_size;

    // Channel for new job broadcasts from the job manager
    let mut job_rx = shared.jobs.subscribe().await;

    // ── Vardiff channel ───────────────────────────────────────────────────────
    // The submit handler lives inside `dispatch` which doesn't hold the write
    // half. We give it a sender so it can signal "push new difficulty" without
    // needing direct access to `w`.
    let (diff_tx, mut diff_rx) = mpsc::unbounded_channel::<f64>();

    loop {
        tokio::select! {

            // ── New difficulty from vardiff ───────────────────────────────────
            Some(new_diff) = diff_rx.recv() => {
                tracing::debug!("[{}] vardiff → {:.1}", addr, new_diff);
                let notif = StratumNotification::new(
                    "mining.set_difficulty",
                    json!([new_diff]),
                );
                send(&mut w, &serde_json::to_value(&notif)?).await?;
            }

            // ── New job broadcast → push mining.notify ────────────────────────
            job = job_rx.recv() => {
                let Some(job) = job else { break; };
                if sess.authorized {
                    let notif = StratumNotification::new(
                        "mining.notify",
                        job.to_notify_params(),
                    );
                    send(&mut w, &serde_json::to_value(&notif)?).await?;
                }
            }

            // ── Inbound line from miner ───────────────────────────────────────
            n = reader.read_line(&mut line) => {
                if n? == 0 { break; } // EOF / disconnect

                let trimmed = line.trim();
                if trimmed.is_empty() { line.clear(); continue; }

                let req: StratumRequest = match serde_json::from_str(trimmed) {
                    Ok(r)  => r,
                    Err(_) => { line.clear(); continue; }
                };

                let id = req.id.clone().unwrap_or(Value::Null);

                let response = dispatch(
                    &req, &mut sess, &shared, &addr, diff_tx.clone()
                ).await;

                let msg = match response {
                    Ok(Some(v)) => v,
                    Ok(None)    => { line.clear(); continue; }
                    Err(e)      => serde_json::to_value(
                        StratumResponse::err(id, 20, &e.to_string())
                    )?,
                };

                send(&mut w, &msg).await?;

                // After authorize succeeds: push current job + initial difficulty
                if sess.authorized && req.method == "mining.authorize" {
                    let coin = sess.coin.as_deref().unwrap_or("TTY");
                    if let Some(job) = shared.jobs.current(coin).await {
                        let notif = StratumNotification::new(
                            "mining.notify",
                            job.to_notify_params(),
                        );
                        send(&mut w, &serde_json::to_value(&notif)?).await?;
                    }
                    let diff = shared.vardiff.current_diff(
                        sess.worker_name.as_deref().unwrap_or("")
                    );
                    let diff_notif = StratumNotification::new(
                        "mining.set_difficulty",
                        json!([diff]),
                    );
                    send(&mut w, &serde_json::to_value(&diff_notif)?).await?;
                }

                line.clear();
            }
        }
    }

    Ok(())
}

async fn dispatch(
    req:     &StratumRequest,
    sess:    &mut Session,
    shared:  &Arc<Shared>,
    addr:    &str,
    diff_tx: mpsc::UnboundedSender<f64>,
) -> Result<Option<Value>> {
    let id = req.id.clone().unwrap_or(Value::Null);

    match req.method.as_str() {

        // ── subscribe ─────────────────────────────────────────────────────────
        "mining.subscribe" => {
            let en1 = gen_extranonce1();
            sess.extranonce1  = Some(en1.clone());
            sess.subscribed   = true;
            let en2_size = sess.extranonce2_size as u64;
            let resp = StratumResponse::ok(id, json!([
                [["mining.notify", &en1]],
                en1,
                en2_size,
            ]));
            Ok(Some(serde_json::to_value(resp)?))
        }

        // ── authorize ─────────────────────────────────────────────────────────
        "mining.authorize" => {
            if !sess.subscribed {
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 24, "not subscribed")
                )?));
            }
            let Ok(p) = AuthorizeParams::try_from(&req.params) else {
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 25, "bad params")
                )?));
            };

            let coin = coin_from_password(&p.password);
            sess.worker_name = Some(p.worker_name.clone());
            sess.coin        = Some(coin.clone());
            sess.authorized  = true;

            tracing::info!("[{}] authorized: {} ({})", addr, p.worker_name, coin);

            let db    = shared.db.clone();
            let wname = p.worker_name.clone();
            let c     = coin.clone();
            tokio::spawn(async move {
                if let Err(e) = db::ensure_worker(&db, &wname, &c).await {
                    tracing::warn!("ensure_worker: {:?}", e);
                }
            });

            Ok(Some(serde_json::to_value(StratumResponse::ok(id, json!(true)))?))
        }

        // ── submit ────────────────────────────────────────────────────────────
        "mining.submit" => {
            if !sess.authorized {
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 24, "unauthorized")
                )?));
            }

            let Ok(p) = SubmitParams::try_from(&req.params) else {
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 25, "bad params")
                )?));
            };

            let coin = sess.coin.as_deref().unwrap_or("TTY");

            let Some(job) = shared.jobs.current(coin).await else {
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 21, "job not found")
                )?));
            };

            if job.id != p.job_id {
                tracing::debug!("[{}] stale job {}", addr, p.job_id);
                return Ok(Some(serde_json::to_value(
                    StratumResponse::err(id, 21, "stale job")
                )?));
            }

            let worker   = sess.worker_name.as_deref().unwrap_or("anonymous");
            let en1      = sess.extranonce1.as_deref().unwrap_or("");
            let cur_diff = shared.vardiff.current_diff(worker);

            let result = shares::validate(
                &job, en1, &p.extranonce2, &p.ntime, &p.nonce, cur_diff
            );

            let (accepted, share_row) = match &result {
                Ok(s) => {
                    if s.is_block {
                        tracing::info!(
                            "[{}] *** BLOCK FOUND *** coin={} height={} hash={}",
                            addr, coin, job.height, s.hash
                        );
                    } else {
                        tracing::debug!("[{}] share accepted diff={:.1}", addr, cur_diff);
                    }
                    let row = ShareRow {
                        worker_name:  worker.to_string(),
                        coin:         coin.to_string(),
                        accepted:     true,
                        difficulty:   cur_diff,
                        submitted_at: Utc::now(),
                        block_height: Some(job.height),
                        nonce:        Some(p.nonce.clone()),
                        hash:         Some(s.hash.clone()),
                        is_block:     s.is_block,
                    };
                    (true, Some(row))
                }
                Err(e) => {
                    tracing::debug!("[{}] share rejected: {}", addr, e);
                    let row = ShareRow {
                        worker_name:  worker.to_string(),
                        coin:         coin.to_string(),
                        accepted:     false,
                        difficulty:   cur_diff,
                        submitted_at: Utc::now(),
                        block_height: Some(job.height),
                        nonce:        Some(p.nonce.clone()),
                        hash:         None,
                        is_block:     false,
                    };
                    (false, Some(row))
                }
            };

            // Fire-and-forget DB write
            if let Some(row) = share_row {
                let db = shared.db.clone();
                tokio::spawn(async move {
                    if let Err(e) = db::insert_share(&db, &row).await {
                        tracing::warn!("insert_share: {:?}", e);
                    }
                });
            }

            // ── Vardiff retarget ──────────────────────────────────────────────
            // on_share() returns Some(new_diff) if a retarget is due.
            // We send it down diff_tx; the select! loop above picks it up
            // and pushes mining.set_difficulty to the miner immediately.
            if let Some(new_diff) = shared.vardiff.on_share(worker) {
                // Non-blocking: if the channel is somehow full the session
                // is already broken, so we just log and continue.
                if diff_tx.send(new_diff).is_err() {
                    tracing::warn!("[{}] diff_tx send failed (session closed?)", addr);
                }
            }

            let resp = if accepted {
                StratumResponse::ok(id, json!(true))
            } else {
                StratumResponse::err(id, 23, "low difficulty share")
            };
            Ok(Some(serde_json::to_value(resp)?))
        }

        // ── extranonce subscribe (optional miner feature) ─────────────────────
        "mining.extranonce.subscribe" => {
            Ok(Some(serde_json::to_value(StratumResponse::ok(id, json!(true)))?))  
        }

        // ── keep-alive / unknown ──────────────────────────────────────────────
        _ => {
            tracing::trace!("[{}] unknown method: {}", addr, req.method);
            Ok(None)
        }
    }
}

async fn send(w: &mut tokio::net::tcp::OwnedWriteHalf, v: &Value) -> Result<()> {
    let mut bytes = serde_json::to_vec(v)?;
    bytes.push(b'\n');
    w.write_all(&bytes).await?;
    Ok(())
}

fn gen_extranonce1() -> String {
    let bytes: [u8; 4] = rand::thread_rng().gen();
    hex::encode(bytes)
}

fn coin_from_password(pass: &str) -> String {
    if pass.to_uppercase().contains("FNNC") {
        "FNNC".to_string()
    } else {
        "TTY".to_string()
    }
}
