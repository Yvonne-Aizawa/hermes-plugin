"""Lumina Plugin tools.

Currently includes HTTP/API request handling and notification support.
Add future Lumina-specific tools here or split into modules such as schemas.py,
handlers.py, and api_client.py as the plugin grows.

HTTP features:
- All HTTP methods (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
- Authentication (Bearer token, Basic auth, API key)
- Custom headers
- JSON and form data support
- File upload support
- Response parsing (JSON, text, headers, status)
- Timeout handling
- Error handling with detailed messages

Notification features:
- Send notifications to ntfy server
- Priority levels (min, low, default, high, urgent)
- Tags and emojis
- Title and message support

Transmute features:
- Inspect possible conversions for a local file
- Convert local files via a self-hosted Transmute API
- Download converted outputs to a local path
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)

try:
    from .avatar_state import get_state, patch_state, validate_state_patch
    from .avatar_timeline import append_events, get_events, last_event_id, protocol, validate_event
except ImportError:
    from avatar_state import get_state, patch_state, validate_state_patch
    from avatar_timeline import append_events, get_events, last_event_id, protocol, validate_event


# Tool schemas (fixed format)
HTTP_REQUEST_SCHEMA = {
    "name": "http_request",
    "description": "Make an HTTP request to a URL with authentication, headers, and response parsing. Supports all HTTP methods, auth (bearer/basic/api_key), JSON/form data, file uploads, query params, and timeout. This should be used for api calls. use your browser_ tools to navigate and inspect pages otherwise",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to make the request to"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                "default": "GET",
                "description": "HTTP method to use",
            },
            "headers": {
                "type": "object",
                "description": "Additional headers to send with the request",
            },
            "json_data": {
                "type": "object",
                "description": "JSON data to send in request body (sets Content-Type: application/json)",
            },
            "form_data": {
                "type": "object",
                "description": "Form data to send (sets Content-Type: application/x-www-form-urlencoded)",
            },
            "files": {
                "type": "object",
                "description": "Files to upload: {'file_key': '/path/to/file'}",
            },
            "auth": {
                "type": "object",
                "description": "Authentication: {'type': 'bearer|basic|api_key', 'value': 'token'}",
            },
            "params": {
                "type": "object",
                "description": "Query parameters to append to URL",
            },
            "timeout": {
                "type": "integer",
                "default": 30,
                "description": "Request timeout in seconds",
            },
            "follow_redirects": {
                "type": "boolean",
                "default": True,
                "description": "Follow HTTP redirects",
            },
        },
        "required": ["url"],
    },
}


# Notification tool schema
SEND_NOTIFICATION_SCHEMA = {
    "name": "send_notification",
    "description": "Send a notification to ntfy server. Supports priority levels (min, low, default, high, urgent), tags/emojis, title and message. Automatically reads ntfy URL and token from environment variables (NTFY_URL, NTFY_TOKEN).",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The ntfy topic to send the notification to",
            },
            "message": {
                "type": "string",
                "description": "The notification message body",
            },
            "title": {
                "type": "string",
                "description": "Optional title for the notification",
            },
            "priority": {
                "type": "string",
                "enum": ["min", "low", "default", "high", "urgent"],
                "default": "default",
                "description": "Priority level of the notification",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of tags/emojis for the notification (e.g., ['warning', 'rocket'])",
            },
            "markdown": {
                "type": "boolean",
                "default": False,
                "description": "Whether to format the message as markdown",
            },
        },
        "required": ["topic", "message"],
    },
}


TRANSMUTE_FILE_CONVERSIONS_SCHEMA = {
    "name": "transmute_file_conversions",
    "description": "Upload a local file to the configured Transmute server and return the formats it can be converted to. Reads TRANSMUTE_URL and TRANSMUTE_API_KEY from the environment.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Absolute or relative path to the local file to inspect",
            },
            "timeout": {
                "type": "integer",
                "default": 120,
                "description": "Request timeout in seconds for the upload call",
            },
        },
        "required": ["input_path"],
    },
}


TRANSMUTE_CONVERT_FILE_SCHEMA = {
    "name": "transmute_convert_file",
    "description": "Convert a local file using the configured Transmute server. Uploads input_path, converts to target_format, downloads the result, and returns the output path.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Absolute or relative path to the local input file",
            },
            "target_format": {
                "type": "string",
                "description": "Target output format without a leading dot, e.g. png, webp, pdf, mp3",
            },
            "output_path": {
                "type": "string",
                "description": "Optional local output path. Defaults to /tmp/hermes_transmute/<input-stem>.<target_format>",
            },
            "quality": {
                "type": "string",
                "description": "Optional quality setting if supported by the conversion, e.g. low, medium, high",
            },
            "overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Whether to overwrite output_path if it already exists",
            },
            "timeout": {
                "type": "integer",
                "default": 120,
                "description": "Request timeout in seconds for upload, conversion, and download calls",
            },
        },
        "required": ["input_path", "target_format"],
    },
}


AVATAR_GET_STATE_SCHEMA = {
    "name": "avatar_get_state",
    "description": "Return Lumina's current renderer-neutral avatar state and protocol metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "include_events": {
                "type": "boolean",
                "default": False,
                "description": "Include currently queued avatar events in the response.",
            },
            "cursor": {
                "type": "string",
                "description": "Optional numeric event cursor; when include_events is true, only events after this id are returned.",
            },
        },
    },
}


AVATAR_EMIT_SCHEMA = {
    "name": "avatar_emit",
    "description": "Update Lumina's avatar state and/or queue ordered renderer events such as speech, expressions, gaze, and VRMA animations. Use this one compact choreography tool instead of many tiny gesture tools.",
    "parameters": {
        "type": "object",
        "properties": {
            "state": {
                "type": "object",
                "description": "Optional avatar state patch: mood, animation, expression, speaking, gesture, or intensity.",
            },
            "events": {
                "type": "array",
                "description": "Optional ordered timeline events. Supported types: speech.say, speech.pause, avatar.animation, avatar.expression, avatar.gaze, avatar.state.",
                "items": {"type": "object"},
            },
            "ttl_ms": {
                "type": "number",
                "description": "Optional event TTL in milliseconds before renderers stop receiving queued events.",
            },
        },
    },
}


def _check_avatar_available() -> tuple[bool, str]:
    """Avatar state/timeline tools are in-process and always available."""
    return True, ""


def _check_http_available() -> tuple[bool, str]:
    """Check if requests library is available."""
    if not HAS_REQUESTS:
        return (
            False,
            "requests library not installed. Install with: pip install requests",
        )
    return True, ""


def _check_notification_available() -> tuple[bool, str]:
    """Check if ntfy configuration is available."""
    if not HAS_REQUESTS:
        return (
            False,
            "requests library not installed. Install with: pip install requests",
        )

    import os

    ntfy_url = os.getenv("NTFY_URL")
    ntfy_token = os.getenv("NTFY_TOKEN")

    if not ntfy_url:
        return False, "NTFY_URL environment variable not set"

    if not ntfy_token:
        return False, "NTFY_TOKEN environment variable not set"

    return True, ""


def _check_transmute_available() -> tuple[bool, str]:
    """Check if Transmute configuration and requests are available."""
    if not HAS_REQUESTS:
        return (
            False,
            "requests library not installed. Install with: pip install requests",
        )

    transmute_url = os.getenv("TRANSMUTE_URL")
    transmute_token = os.getenv("TRANSMUTE_API_KEY")

    if not transmute_url:
        return False, "TRANSMUTE_URL environment variable not set"

    if not transmute_token:
        return False, "TRANSMUTE_API_KEY environment variable not set"

    return True, ""


def _transmute_config() -> tuple[str, str]:
    """Return normalized Transmute base URL and API token."""
    base_url = (os.getenv("TRANSMUTE_URL") or "").rstrip("/")
    token = os.getenv("TRANSMUTE_API_KEY") or ""
    return base_url, token


def _transmute_headers() -> Dict[str, str]:
    """Build Transmute auth headers."""
    _, token = _transmute_config()
    return {"Authorization": f"Bearer {token}"}


def _transmute_upload_file(input_path: Path, timeout: int = 120) -> Dict[str, Any]:
    """Upload a local file to Transmute and return the JSON response."""
    base_url, _ = _transmute_config()
    with input_path.open("rb") as file_handle:
        response = requests.post(
            f"{base_url}/api/files",
            headers=_transmute_headers(),
            files={"file": (input_path.name, file_handle)},
            timeout=timeout,
        )
    if not response.ok:
        raise RuntimeError(
            f"Upload failed: {response.status_code} {response.text[:500]}"
        )
    return response.json()


def _transmute_convert_uploaded_file(
    file_id: str,
    target_format: str,
    quality: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Convert an uploaded Transmute file and return converted file metadata."""
    base_url, _ = _transmute_config()
    payload: Dict[str, Any] = {"id": file_id, "output_format": target_format}
    if quality:
        payload["quality"] = quality
    response = requests.post(
        f"{base_url}/api/conversions",
        headers={**_transmute_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(
            f"Conversion failed: {response.status_code} {response.text[:500]}"
        )
    return response.json()


def _transmute_download_file(
    file_id: str, output_path: Path, timeout: int = 120
) -> Dict[str, Any]:
    """Download a Transmute file to output_path."""
    base_url, _ = _transmute_config()
    response = requests.get(
        f"{base_url}/api/files/{file_id}",
        headers=_transmute_headers(),
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(
            f"Download failed: {response.status_code} {response.text[:500]}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return {
        "content_type": response.headers.get("Content-Type"),
        "size_bytes": len(response.content),
    }


def _normalize_path(path_value: str) -> Path:
    """Expand user vars and return an absolute-ish Path without requiring resolve()."""
    return Path(os.path.expandvars(os.path.expanduser(path_value)))


def _default_transmute_output_path(input_path: Path, target_format: str) -> Path:
    """Build default Transmute output path."""
    safe_format = target_format.lower().lstrip(".")
    return Path("/tmp/hermes_transmute") / f"{input_path.stem}.{safe_format}"


def _prepare_auth(auth: Optional[Dict[str, str]]) -> Optional[Union[Dict, tuple]]:
    """Prepare authentication object for requests."""
    if not auth:
        return None

    auth_type = auth.get("type", "").lower()
    auth_value = auth.get("value", "")

    if auth_type == "bearer":
        return {"Authorization": f"Bearer {auth_value}"}
    elif auth_type == "basic":
        # Basic auth format: "username:password"
        if ":" in auth_value:
            username, password = auth_value.split(":", 1)
            return (username, password)
    elif auth_type == "api_key":
        # API key format: {"header": "X-API-Key", "value": "secret"}
        header_name = auth.get("header", "X-API-Key")
        return {header_name: auth_value}

    return None


def _handle_response(response: requests.Response) -> Dict[str, Any]:
    """Handle HTTP response and parse into structured format."""
    result = {
        "status": response.status_code,
        "ok": response.ok,
        "reason": response.reason,
        "headers": dict(response.headers),
        "url": response.url,
        "elapsed": response.elapsed.total_seconds(),
        "size": len(response.content),
    }

    # Try to parse JSON response
    try:
        result["json"] = response.json()
    except (ValueError, json.JSONDecodeError):
        result["json"] = None

    # Always include text
    try:
        result["text"] = response.text
    except UnicodeDecodeError:
        result["text"] = "<binary content>"

    return result


def _handle_http_request(args: Dict, **kw) -> str:
    """Make HTTP request with comprehensive options."""

    # Extract arguments
    url = args.get("url")
    method = args.get("method", "GET")
    headers = args.get("headers")
    json_data = args.get("json_data")
    form_data = args.get("form_data")
    files = args.get("files")
    auth = args.get("auth")
    params = args.get("params")
    timeout = args.get("timeout", 30)
    follow_redirects = args.get("follow_redirects", True)

    # Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}")
    except Exception as e:
        return json.dumps({"error": f"URL parsing error: {e}"})

    # Prepare headers
    request_headers = headers or {}

    # Prepare authentication
    auth_obj = None
    auth_headers = None

    if auth:
        auth_result = _prepare_auth(auth)
        if isinstance(auth_result, dict) and "Authorization" in auth_result:
            auth_headers = auth_result
        elif isinstance(auth_result, dict) and len(auth_result) == 1:
            # API key type
            key = list(auth_result.keys())[0]
            request_headers[key] = auth_result[key]
        elif isinstance(auth_result, tuple):
            # Basic auth
            auth_obj = auth_result

    if auth_headers:
        request_headers.update(auth_headers)

    # Prepare request kwargs
    kwargs = {
        "method": method.upper(),
        "url": url,
        "headers": request_headers,
        "timeout": timeout,
        "allow_redirects": follow_redirects,
    }

    # Add request body
    if json_data:
        kwargs["json"] = json_data
    elif form_data:
        kwargs["data"] = form_data

    # Add query parameters
    if params:
        kwargs["params"] = params

    # Add files
    if files:
        file_dict = {}
        for key, file_path in files.items():
            try:
                file_dict[key] = open(file_path, "rb")
            except Exception as e:
                logger.warning(f"Failed to open file {file_path}: {e}")
        kwargs["files"] = file_dict

    # Add basic auth
    if auth_obj:
        kwargs["auth"] = auth_obj

    logger.info(f"Making {method} request to {url}")

    # Make request
    try:
        response = requests.request(**kwargs)
        result = _handle_response(response)
        logger.info(f"Request completed: {response.status_code} {response.reason}")
        return json.dumps(result)

    except requests.exceptions.Timeout:
        return json.dumps({"error": f"Request timed out after {timeout} seconds"})
    except requests.exceptions.ConnectionError as e:
        return json.dumps({"error": f"Connection failed: {e}"})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"HTTP request failed: {e}"})
    finally:
        # Close any opened files
        if files and "files" in kwargs:
            for f in kwargs["files"].values():
                if hasattr(f, "close"):
                    f.close()


def _handle_avatar_get_state(args: Dict, **kw) -> str:
    """Return the current avatar snapshot and renderer protocol metadata."""
    try:
        include_events = bool(args.get("include_events", False))
        cursor = args.get("cursor")
        result: Dict[str, Any] = {
            "success": True,
            "state": get_state(),
            "protocol": protocol(),
            "last_event_id": last_event_id(),
        }
        if include_events:
            result["events"] = get_events(cursor)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": f"avatar_get_state failed: {e}"})


def _handle_avatar_emit(args: Dict, **kw) -> str:
    """Patch avatar state and/or append ordered avatar timeline events."""
    try:
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        state_patch = args.get("state")
        events = args.get("events")
        ttl_ms = args.get("ttl_ms")

        if state_patch is None and not events:
            raise ValueError("provide state, events, or both")

        # Validate before mutating state or appending events so bad choreography
        # does not leave partial visible changes behind.
        if state_patch is not None:
            validate_state_patch(state_patch)
        if events is not None:
            if not isinstance(events, list):
                raise ValueError("events must be an array")
            for event in events:
                validate_event(event)

        state = patch_state(state_patch)
        appended = append_events(events, ttl_ms=ttl_ms)
        return json.dumps(
            {
                "success": True,
                "state": state,
                "events": appended,
                "last_event_id": last_event_id(),
                "protocol": protocol(),
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": f"avatar_emit failed: {e}"})


def _handle_send_notification(args: Dict, **kw) -> str:
    """Send notification to ntfy server."""

    # Extract arguments
    topic = args.get("topic")
    message = args.get("message")
    title = args.get("title")
    priority = args.get("priority", "default")
    tags = args.get("tags")
    markdown = args.get("markdown", False)

    # Read ntfy config from environment
    ntfy_url = os.getenv("NTFY_URL")
    ntfy_token = os.getenv("NTFY_TOKEN")

    # Validate configuration
    if not ntfy_url:
        return json.dumps({"error": "NTFY_URL environment variable not set"})

    if not ntfy_token:
        return json.dumps({"error": "NTFY_TOKEN environment variable not set"})

    # Validate required fields
    if not topic:
        return json.dumps({"error": "topic is required"})

    if not message:
        return json.dumps({"error": "message is required"})

    # Build the full URL for the topic
    # Ensure ntfy_url doesn't have trailing slash and topic doesn't have leading slash
    base_url = ntfy_url.rstrip("/")
    topic_path = topic.lstrip("/")
    url = f"{base_url}/{topic_path}"

    # Prepare headers
    headers = {"Authorization": f"Bearer {ntfy_token}"}

    # Add optional fields
    if title:
        headers["Title"] = title

    if priority:
        headers["Priority"] = priority

    if tags and isinstance(tags, list):
        headers["Tags"] = ",".join(str(tag) for tag in tags)

    if markdown:
        headers["Markdown"] = "yes"

    logger.info(f"Sending notification to topic '{topic}' on {ntfy_url}")

    # Make request
    try:
        response = requests.post(url, data=message, headers=headers, timeout=30)
        result = _handle_response(response)
        logger.info(f"Notification sent: {response.status_code}")
        return json.dumps(result)

    except requests.exceptions.Timeout:
        return json.dumps({"error": "Notification request timed out"})
    except requests.exceptions.ConnectionError as e:
        return json.dumps({"error": f"Connection to ntfy server failed: {e}"})
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Failed to send notification: {e}"})


def _handle_transmute_file_conversions(args: Dict, **kw) -> str:
    """Upload a file to Transmute and return its compatible output formats."""
    input_path_value = args.get("input_path")
    timeout = args.get("timeout", 120)

    if not input_path_value:
        return json.dumps({"error": "input_path is required"})

    available, error = _check_transmute_available()
    if not available:
        return json.dumps({"error": error})

    input_path = _normalize_path(input_path_value)
    if not input_path.exists():
        return json.dumps({"error": f"input_path does not exist: {input_path}"})
    if not input_path.is_file():
        return json.dumps({"error": f"input_path is not a file: {input_path}"})

    try:
        upload = _transmute_upload_file(input_path, timeout=timeout)
        metadata = upload.get("metadata", {})
        compatible_formats = metadata.get("compatible_formats", {})
        result = {
            "success": True,
            "input_path": str(input_path),
            "source_file_id": metadata.get("id"),
            "original_filename": metadata.get("original_filename"),
            "source_format": metadata.get("media_type") or metadata.get("extension"),
            "size_bytes": metadata.get("size_bytes"),
            "sha256_checksum": metadata.get("sha256_checksum"),
            "compatible_formats": compatible_formats,
            "format_count": len(compatible_formats)
            if isinstance(compatible_formats, dict)
            else None,
        }
        return json.dumps(result)
    except requests.exceptions.Timeout:
        return json.dumps(
            {"error": f"Transmute request timed out after {timeout} seconds"}
        )
    except requests.exceptions.ConnectionError as e:
        return json.dumps({"error": f"Connection to Transmute failed: {e}"})
    except Exception as e:
        return json.dumps({"error": f"transmute_file_conversions failed: {e}"})


def _handle_transmute_convert_file(args: Dict, **kw) -> str:
    """Convert a local file with Transmute and return the downloaded output path."""
    input_path_value = args.get("input_path")
    target_format = (args.get("target_format") or "").lower().lstrip(".").strip()
    output_path_value = args.get("output_path")
    quality = args.get("quality")
    overwrite = args.get("overwrite", False)
    timeout = args.get("timeout", 120)

    if not input_path_value:
        return json.dumps({"error": "input_path is required"})
    if not target_format:
        return json.dumps({"error": "target_format is required"})

    available, error = _check_transmute_available()
    if not available:
        return json.dumps({"error": error})

    input_path = _normalize_path(input_path_value)
    if not input_path.exists():
        return json.dumps({"error": f"input_path does not exist: {input_path}"})
    if not input_path.is_file():
        return json.dumps({"error": f"input_path is not a file: {input_path}"})

    output_path = (
        _normalize_path(output_path_value)
        if output_path_value
        else _default_transmute_output_path(input_path, target_format)
    )
    if output_path.exists() and not overwrite:
        return json.dumps(
            {
                "error": f"output_path already exists: {output_path}. Set overwrite=true to replace it."
            }
        )

    try:
        upload = _transmute_upload_file(input_path, timeout=timeout)
        source_metadata = upload.get("metadata", {})
        source_file_id = source_metadata.get("id")
        compatible_formats = source_metadata.get("compatible_formats", {})

        if not source_file_id:
            return json.dumps(
                {
                    "error": "Transmute upload did not return a source file id",
                    "upload": upload,
                }
            )

        if (
            isinstance(compatible_formats, dict)
            and target_format not in compatible_formats
        ):
            return json.dumps(
                {
                    "error": f"target_format '{target_format}' is not listed as compatible for this file",
                    "input_path": str(input_path),
                    "source_format": source_metadata.get("media_type")
                    or source_metadata.get("extension"),
                    "compatible_formats": compatible_formats,
                }
            )

        if quality and isinstance(compatible_formats, dict):
            allowed_qualities = compatible_formats.get(target_format) or []
            if allowed_qualities and quality not in allowed_qualities:
                return json.dumps(
                    {
                        "error": f"quality '{quality}' is not listed as compatible for target_format '{target_format}'",
                        "allowed_qualities": allowed_qualities,
                    }
                )

        converted_metadata = _transmute_convert_uploaded_file(
            source_file_id,
            target_format,
            quality=quality,
            timeout=timeout,
        )
        converted_file_id = converted_metadata.get("id")
        if not converted_file_id:
            return json.dumps(
                {
                    "error": "Transmute conversion did not return a converted file id",
                    "conversion": converted_metadata,
                }
            )

        download = _transmute_download_file(
            converted_file_id, output_path, timeout=timeout
        )
        result = {
            "success": True,
            "input_path": str(input_path),
            "output_path": str(output_path),
            "target_format": target_format,
            "quality": quality,
            "source_file_id": source_file_id,
            "converted_file_id": converted_file_id,
            "source_metadata": source_metadata,
            "converted_metadata": converted_metadata,
            "download": download,
        }
        return json.dumps(result)
    except requests.exceptions.Timeout:
        return json.dumps(
            {"error": f"Transmute request timed out after {timeout} seconds"}
        )
    except requests.exceptions.ConnectionError as e:
        return json.dumps({"error": f"Connection to Transmute failed: {e}"})
    except Exception as e:
        return json.dumps({"error": f"transmute_convert_file failed: {e}"})
