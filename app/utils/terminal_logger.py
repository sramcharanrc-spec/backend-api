import logging
import traceback
from datetime import datetime
from time import perf_counter

logger = logging.getLogger("terminal")
logger.setLevel(logging.INFO)

EMOJI_START = "🚀"
EMOJI_FILE = "📄"
EMOJI_UPLOAD = "⬆️"
EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_PROCESSING = "🔍"
EMOJI_EXTRACTION = "🧠"
EMOJI_QUEUE = "📦"
EMOJI_COMPLETED = "🏁"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_file_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unknown"
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def log_terminal(message: str, emoji: str = EMOJI_PROCESSING) -> None:
    line = f"[{_timestamp()}] {emoji} {message}"
    print(line, flush=True)
    logger.info(line)


def log_exception(step: str, error: Exception, step_number: int | None = None) -> None:
    prefix = f"[STEP {step_number}] " if step_number is not None else ""
    log_terminal(f"{prefix}Failure step: {step}", EMOJI_ERROR)
    log_terminal(f"{prefix}Exception: {error}", EMOJI_ERROR)
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    log_terminal(f"{prefix}Traceback:\n{trace}", EMOJI_ERROR)


class TerminalStepLogger:
    def __init__(self, flow_name: str):
        self.flow_name = flow_name
        self.step = 0
        self.started_at = perf_counter()

    def log(self, message: str, emoji: str = EMOJI_PROCESSING) -> None:
        self.step += 1
        log_terminal(f"[STEP {self.step}] {message}", emoji)

    def error(self, step: str, error: Exception) -> None:
        log_exception(step, error, self.step + 1)

    def elapsed_seconds(self) -> float:
        return perf_counter() - self.started_at

    def completed(self, message: str = "Completed") -> None:
        self.log(f"{message} | Total execution time: {self.elapsed_seconds():.2f}s", EMOJI_COMPLETED)
