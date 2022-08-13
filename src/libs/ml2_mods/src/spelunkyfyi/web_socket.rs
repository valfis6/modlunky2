use std::path::Path;
use std::time::Duration;

use anyhow::anyhow;
use async_trait::async_trait;
use derivative::Derivative;
use futures_util::{SinkExt as _, StreamExt as _};
use http::{
    header::{AUTHORIZATION, CONNECTION, HOST, SEC_WEBSOCKET_KEY, SEC_WEBSOCKET_VERSION, UPGRADE},
    HeaderValue, Request, StatusCode, Uri,
};
use ml2_net::backoff::{AsBackoffKind, BackoffKind, ExponentialBackoffBuilder, RetryPolicy};
use rand::distributions::Uniform;
use rand::{Rng, RngCore};
use serde::{Deserialize, Serialize};
use tokio::{net::TcpStream, select, time};
use tokio_graceful_shutdown::{IntoSubsystem, SubsystemHandle};
use tokio_tungstenite::{
    tungstenite::{
        handshake::client::generate_key, protocol::WebSocketConfig, Error as WsError, Message,
    },
    MaybeTlsStream, WebSocketStream,
};
use tracing::{debug, info, instrument, trace, warn};

use crate::manager::{ModManagerHandle, ModSource};

use super::{Error, Result};

pub const DEFAULT_MIN_PING_INTERVAL: Duration = Duration::from_secs(15);
pub const DEFAULT_MAX_PING_INTERVAL: Duration = Duration::from_secs(25);
pub const DEFAULT_PONG_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
struct ChannelMessage {
    action: String,
    channel_name: String,
    data: Option<MessageData>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
struct MessageData {
    install_code: String,
    mod_file_id: String,
}

#[derive(Debug)]
enum Check {
    Ping(),
    Pong(),
}

#[derive(Derivative)]
#[derivative(Debug)]
pub struct WebSocketClient {
    #[derivative(Debug = "ignore")]
    authz_value: HeaderValue,
    manager_handle: ModManagerHandle,
    ping_interval_dist: Uniform<Duration>,
    pong_timeout: Duration,
    service_uri: Uri,
    retry_policy: RetryPolicy,
}

impl WebSocketClient {
    pub fn new(
        service_root: &str,
        auth_token: &str,
        manager_handle: ModManagerHandle,
        ping_interval_dist: Uniform<Duration>,
        pong_timeout: Duration,
    ) -> Result<Self> {
        let backoff = ExponentialBackoffBuilder::default()
            .with_max_elapsed_time(None)
            .build();

        Ok(WebSocketClient {
            authz_value: HeaderValue::from_str(&format!("Token {}", auth_token))?,
            manager_handle,
            ping_interval_dist,
            pong_timeout,
            retry_policy: RetryPolicy::new(backoff),
            service_uri: root_to_service_uri(service_root)?,
        })
    }

    #[instrument(skip_all)]
    async fn connect_and_run(
        &self,
        subsys: &SubsystemHandle,
    ) -> std::result::Result<(), ConnectionError> {
        debug!("Attempting to connect to {:?}", self.service_uri);
        // Tungstenite checks for various headers, but doesn't have a way to get a Builder or
        // constants we can re-use. We have to build the Request so we can set the authz header
        let request = Request::get(&self.service_uri)
            .version(http::Version::HTTP_11)
            .header(HOST, self.service_uri.authority().unwrap().as_str())
            .header(AUTHORIZATION, &self.authz_value)
            .header(CONNECTION, "Upgrade")
            .header(UPGRADE, "websocket")
            .header(SEC_WEBSOCKET_VERSION, "13")
            .header(SEC_WEBSOCKET_KEY, generate_key())
            .body(())?;

        // This is the maximum number of messages that will be queued in Tungstenite. This doesn't
        // include pong or close messages. All messages are buffered before they're written. So,
        // the smallest functional value is 1. Notably, the size of the messages and the underlying
        // TCP send buffer aren't considered.
        let config = WebSocketConfig {
            max_send_queue: Some(2),
            ..Default::default()
        };

        let mut stream = tokio_tungstenite::connect_async_with_config(request, Some(config))
            .await
            .map(|v| v.0)?;
        debug!("WebSocket connected");

        let mut check_state = Check::Ping();
        let mut check_sleep = Box::pin(time::sleep(
            rand::thread_rng().sample(self.ping_interval_dist),
        ));

        loop {
            select! {
                _ = subsys.on_shutdown_requested() => {
                    stream.close(None).await.map_err(|e| {
                        debug!("Error trying to close WebSocket: {:?}",  e);
                        e
                    })?;
                    break
                },
                () = (&mut check_sleep) => match check_state {
                    Check::Ping() => {
                        trace!("Time to send a ping");
                        let mut payload = vec![0_u8; 8];
                        rand::thread_rng().fill_bytes(&mut payload[..]);
                        stream
                            .send(Message::Ping(payload))
                            .await?;
                        check_state = Check::Pong();
                        check_sleep = Box::pin(time::sleep(self.pong_timeout));
                    }
                    Check::Pong() => {
                        debug!("Timed out waiting for WebSocket pong");
                        // Timed out, start reconnecting
                        return Ok(());
                    }
                },
                Some(msg) = stream.next() => match msg? {
                    Message::Ping(_) => {
                        // Responding Pong is enqueued by Tungstenite
                        trace!("Received ping from server");
                    },
                    Message::Pong(_) => {
                        trace!("Received a pong");
                        // Note that we acccept any pong. This is fine since we're just keeping
                        // the connection alive, not measuring latency.
                        check_state = Check::Ping();
                        check_sleep =
                            Box::pin(time::sleep(rand::thread_rng().sample(self.ping_interval_dist)));
                    },
                    Message::Close(_) => {
                        debug!("WebSocket closed");
                        // Responding Close is enqueued by Tungstenite
                        break;
                    },
                    Message::Text(json) => self.handle_json(&mut stream, json.as_bytes()).await?,
                    Message::Binary(json) => self.handle_json(&mut stream, &json[..]).await?,
                    Message::Frame(_) => {
                        warn!("Rececived unexpected Frame message from WebSocket");
                    },
                }
            }
        }
        Ok(())
    }

    async fn handle_json(
        &self,
        stream: &mut WebSocketStream<MaybeTlsStream<TcpStream>>,
        json: &[u8],
    ) -> std::result::Result<(), ConnectionError> {
        debug!(
            "Parsing JSON message {:?}",
            std::str::from_utf8(json)
                .ok()
                .unwrap_or("(UTF-8 conversion failed)")
        );
        let msg = serde_json::from_slice::<ChannelMessage>(json);
        if let Err(e) = msg {
            warn!("Failed to parse WebSocket message from server: {:?}", e);
            return Ok(());
        }
        let msg = msg.unwrap();
        match msg.action.as_str() {
            "web-connected" | "hello" => {
                debug!("Received channel greeting of type {:?}", msg.action);
                send_message(
                    stream,
                    ChannelMessage {
                        action: "announce".to_string(),
                        channel_name: msg.channel_name.clone(),
                        data: None,
                    },
                )
                .await?;
            }
            "web-disconnected" => {
                debug!("Received channel parting");
            } // Nothing
            "install" => {
                info!("Received install request: {:?}", msg);
                match msg.data {
                    None => warn!("WebSocket received install message without data"),
                    Some(data) => {
                        let res = self
                            .manager_handle
                            .install(&ModSource::Remote {
                                code: data.install_code,
                            })
                            .await;
                        if let Err(e) = res {
                            // Note that this error has nothing to do with the WebSocket
                            warn!("Installing mod via WebSocket failed: {:?}", e);
                        } else {
                            send_message(
                                stream,
                                ChannelMessage {
                                    action: "install-complete".to_string(),
                                    channel_name: msg.channel_name.clone(),
                                    data: None,
                                },
                            )
                            .await?;
                        }
                    }
                }
            }
            _ => {
                warn!(
                    "Received WebSocket message from server with unrecognized action {:?}",
                    msg.action
                );
            }
        }
        Ok(())
    }
}

async fn send_message(
    stream: &mut WebSocketStream<MaybeTlsStream<TcpStream>>,
    msg: ChannelMessage,
) -> std::result::Result<(), ConnectionError> {
    let reply = serde_json::to_string(&msg)?;
    stream.send(Message::Text(reply)).await?;
    Ok(())
}

#[derive(Debug, thiserror::Error)]
enum ConnectionError {
    #[error(transparent)]
    HttpRequestError(#[from] http::Error),
    #[error(transparent)]
    JsonError(#[from] serde_json::Error),
    #[error(transparent)]
    WebSocketError(#[from] WsError),
}

impl From<ConnectionError> for Error {
    fn from(err: ConnectionError) -> Self {
        match err {
            ConnectionError::HttpRequestError(inner) => inner.into(),
            ConnectionError::JsonError(inner) => inner.into(),
            ConnectionError::WebSocketError(inner) => inner.into(),
        }
    }
}

impl AsBackoffKind for ConnectionError {
    fn as_backoff_kind(&self) -> BackoffKind {
        match self {
            ConnectionError::JsonError(_) => BackoffKind::Permanent,
            ConnectionError::HttpRequestError(_) => BackoffKind::Permanent,
            ConnectionError::WebSocketError(inner) => match &inner {
                &WsError::Http(resp) => {
                    let status = resp.status();
                    match status {
                        StatusCode::TOO_MANY_REQUESTS
                        | StatusCode::SERVICE_UNAVAILABLE
                        | StatusCode::GATEWAY_TIMEOUT => BackoffKind::Transient,
                        _ => BackoffKind::Permanent,
                    }
                }
                &WsError::Io(_) => BackoffKind::Transient,
                _ => BackoffKind::Permanent,
            },
        }
    }
}

#[async_trait]
impl IntoSubsystem<Error> for WebSocketClient {
    async fn run(mut self, subsys: SubsystemHandle) -> Result<()> {
        let mut last_result = Ok(());

        loop {
            select! {
                _ = subsys.on_shutdown_requested() => break,
                () = self.retry_policy.wait_to_retry(last_result)? => {
                    last_result = self.connect_and_run(&subsys).await;
                    // This is complicated because we want to indicate a problem with configuration
                    // when it's an HTTP error with status 403 Forbidden
                    if let Err(e) = &last_result {
                        if let Err(ConnectionError::WebSocketError(WsError::Http(resp))) = &last_result {
                            if resp.status() == StatusCode::FORBIDDEN {
                                warn!("WebSocket authorization failed. Incorrect token?");
                            }
                        }
                        info!("WebSocket connection error: {:?}", e);
                    }
                }
            }
        }
        Ok(())
    }
}

fn root_to_service_uri(service_root: &str) -> Result<Uri> {
    let service_root = service_root.parse::<Uri>()?;
    let scheme = match service_root.scheme().map(|s| s.as_str()).unwrap_or("ws") {
        "http" => "ws",
        "https" => "wss",
        "ws" => "ws",
        "wss" => "wss",
        _ => {
            return Err(Error::UnknownError(anyhow!(
                "Unknown service scheme {:?}",
                service_root.scheme()
            )))
        }
    };

    let path = Path::new(service_root.path()).join("ws/gateway/ml/");
    let path = path
        .to_str()
        .ok_or_else(|| Error::InvalidUri(anyhow!("Failed to convert {:?}", path)))?;

    let mut parts = service_root.into_parts();
    parts.scheme = Some(scheme.try_into()?);
    parts.path_and_query = Some(path.try_into()?);
    Ok(Uri::from_parts(parts)?)
}
