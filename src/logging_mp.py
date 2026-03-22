"""
multi-processing Logging
Uses standard logging module and reads parameters from cfg_json_str.
Main features:
1. xxx-1.log is always the current latest log file.
2. Each run starts a fresh log file (overwrites xxx-1.log after rotating older ones).
"""

import logging
import logging.handlers
import json
import sys
import shutil
import os
import threading
import multiprocessing
import re
from pathlib import Path
from typing import Any, Dict, Optional

# Global variables to track initialization state within the process
_initialization_lock = threading.Lock()
_initialized_pid = None

'''
    logger config example:
    "logging": {
        "level": "DEBUG",
        "log_file": "<module.name>",
        "output": "file, console",
        "log_base": "qlib-",
        "max_size": "1024*1024*10",
        "max_index": 9
    },
'''

def load_logging_config(cfg_json_str: Optional[str] = None) -> Dict[str, Any]:
    """Load logging parameters from a json string.

    Supported forms:
    - Full JSON object: '{"logging": {...}}' or '{...logging fields...}'
    - Logging fragment: '"logging": {...},'
    """
    if not cfg_json_str:
        return {}

    raw = cfg_json_str.strip()
    if not raw:
        return {}

    # Accept fragment style and trailing commas.
    candidate = raw
    if not candidate.startswith("{"):
        candidate = "{" + candidate + "}"
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    candidate = re.sub(r",\s*$", "", candidate)

    try:
        conf = json.loads(candidate)
    except Exception:
        return {}

    if not isinstance(conf, dict):
        return {}

    if "logging" in conf and isinstance(conf["logging"], dict):
        return conf["logging"]
    return conf

def rotate_numbered_logs(directory: Path, base_name: str, extension: str, max_index: int = 9) -> Path:
    """Rotate existing numbered logs and return the path for the new log (base-1.ext).
    
    This shifts base-(i-1).ext -> base-i.ext for i from max_index down to 2,
    then ensures base-1.ext is available for the new log file.
    """
    # Move from highest to lowest to avoid clobbering
    for i in range(max_index, 1, -1):
        src = directory / f"{base_name}-{i-1}{extension}"
        dst = directory / f"{base_name}-{i}{extension}"
        if src.exists():
            try:
                if dst.exists():
                    dst.unlink()
                src.replace(dst)
            except Exception:
                # Best-effort: try shutil.move as fallback
                try:
                    shutil.move(str(src), str(dst))
                except Exception:
                    pass

    # New log is base-1.ext
    new_log = directory / f"{base_name}-1{extension}"
    # If base-1 still exists unexpectedly, remove it (it should have been moved)
    if new_log.exists():
        try:
            new_log.unlink()
        except Exception:
            try:
                # In some cases, unlink might fail if file is locked
                with open(new_log, 'w') as f:
                    f.truncate(0)
            except Exception:
                pass
    return new_log

def cleanup_old_group_logs(directory: Path, prefix: str, current_base: str, max_count: int):
    """
    Clean up logs matching 'prefix*' that do not belong to 'current_base', 
    to ensure total files (current + others) <= max_count.
    Prioritize keeping current files, then newest other files.
    """
    try:
        # Glob patterns are simple, but we need strict prefix matching
        # prefix e.g. "qlib-train_sample_model"
        # file e.g. "qlib-train_sample_model-12345-1.log"
        candidates = [f for f in directory.iterdir() if f.name.startswith(prefix) and f.suffix == '.log']
        
        current_run_files = []
        other_run_files = []
        
        for f in candidates:
            # Check if it belongs to current run (starts with current_base-)
            # current_base e.g. "qlib-train_sample_model-12345"
            # We add "-" to ensure we don't accidentally match "qlib-train_sample_model-123456"
            if f.name.startswith(f"{current_base}-"):
                current_run_files.append(f)
            else:
                other_run_files.append(f)
                
        current_cnt = len(current_run_files)
        # Assuming current run will take at least 1 slot soon
        effective_current = max(1, current_cnt) 
        
        remaining = max_count - effective_current
        if remaining < 0:
            remaining = 0
            
        if len(other_run_files) > remaining:
            # Sort by mtime, oldest first
            other_run_files.sort(key=lambda x: x.stat().st_mtime)
            num_to_delete = len(other_run_files) - remaining
            
            for f in other_run_files[:num_to_delete]:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

class NumberedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Custom RotatingFileHandler that uses -1.log, -2.log naming scheme."""
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        
        base_path = Path(self.baseFilename)
        directory = base_path.parent
        # Expecting filename to end with -1.log
        if base_path.name.endswith("-1.log"):
            base_name = base_path.name[:-6]
            extension = ".log"
            rotate_numbered_logs(directory, base_name, extension, self.backupCount + 1)
        
        if not self.delay:
            self.stream = self._open()

def setup_logging(
    name: Optional[str] = None,
    skip_rotation: bool = False,
    is_subprocess: Optional[bool] = None,
    cfg_json_str: Optional[str] = None,
) -> logging.Logger:
    """Setup standard logging with manual rotation and multi-process support.
    
    Args:
        name: Optional logger name. If not provided, uses script name.
        skip_rotation: If True, skip manual rotation at startup.
        is_subprocess: Explicitly specify if this is a sub-process. If None, auto-detect.
        cfg_json_str: Logging json string.
    """
    global _initialized_pid
    
    current_pid = os.getpid()
    with _initialization_lock:
        if _initialized_pid == current_pid and name is None:
            return logging.getLogger()
        
        log_cfg = load_logging_config(cfg_json_str)
        
        # Config values
        log_level_str = log_cfg.get("level", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        log_base = log_cfg.get("log_base", "")
        log_file_tmpl = log_cfg.get("log_file", "<module.name>")
        max_index = int(log_cfg.get("max_index", 9))
        output_modes = [m.strip().lower() for m in log_cfg.get("output", "file, console").split(",")]
        
        # Identify module name
        if name:
            module_name = name
        elif hasattr(sys, 'argv') and sys.argv[0]:
            module_name = Path(sys.argv[0]).stem
        else:
            module_name = "unknown"
        
        # Group Prefix (e.g. qlib-train_sample_model)
        base_suffix = log_file_tmpl.replace("<module.name>", module_name)
        log_prefix_group = f"{log_base}{base_suffix}"
        
        # Multi-process / Sub-process support
        main_pid_env = os.environ.get("QLIB_MAIN_PID")
        
        if is_subprocess is None:
            if main_pid_env and int(main_pid_env) != current_pid:
                actual_is_subprocess = True
                main_pid = int(main_pid_env)
            else:
                is_mp_child = (multiprocessing.current_process().name != 'MainProcess')
                if is_mp_child:
                    actual_is_subprocess = True
                    main_pid = os.getppid()
                else:
                    actual_is_subprocess = False
                    main_pid = current_pid
                    os.environ["QLIB_MAIN_PID"] = str(current_pid)
        else:
            actual_is_subprocess = is_subprocess
            main_pid = int(main_pid_env) if main_pid_env else current_pid

        if actual_is_subprocess:
            combined_log_base = f"{log_prefix_group}-{main_pid}"
        else:
            combined_log_base = log_prefix_group
        
        # Get root logger
        logger = logging.getLogger()
        logger.setLevel(log_level)
        while logger.handlers:
            logger.removeHandler(logger.handlers[0])
        
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        if "console" in output_modes:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        if "file" in output_modes:
            project_root = Path(__file__).resolve().parent.parent
            log_dir = project_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # --- START CLEANUP ---
            # Ensure total log files for this module do not exceed max_index
            cleanup_old_group_logs(log_dir, log_prefix_group, combined_log_base, max_index)
            # --- END CLEANUP ---
            
            extension = ".log"
            if not skip_rotation and not actual_is_subprocess:
                log_path = rotate_numbered_logs(log_dir, combined_log_base, extension, max_index)
                mode = 'w'
            else:
                log_path = log_dir / f"{combined_log_base}-1{extension}"
                mode = 'a'
            
            # Get max_size from config, support string expressions like "1024*1024*10"
            max_size_config = log_cfg.get("max_size", "100*1024*1024")  # Default 100MB
            if isinstance(max_size_config, str):
                try:
                    # Safely evaluate simple arithmetic expressions
                    max_bytes = int(eval(max_size_config, {"__builtins__": {}}, {}))
                except Exception:
                    # Fallback to default if evaluation fails
                    max_bytes = 100 * 1024 * 1024
            else:
                max_bytes = int(max_size_config)
            
            file_handler = NumberedRotatingFileHandler(
                log_path, mode=mode, encoding="utf-8", 
                maxBytes=max_bytes, backupCount=max_index-1
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            if _initialized_pid != current_pid:
                logger.info(f"Logging initialized for {module_name} (PID: {current_pid})")
                logger.info(f"Current log file: {log_path.name}")
        else:
            if _initialized_pid != current_pid:
                logger.info(f"Logging initialized for {module_name} (Console only)")
        
        # Suppress Qlib default logging
        try:
            from qlib.config import C
            def disable_qlib_file_logging(conf):
                if isinstance(conf, dict) and "logging_config" in conf:
                    lc = conf["logging_config"]
                    if "handlers" in lc:
                        lc["handlers"].pop("file", None)
                    if "loggers" in lc and "qlib" in lc["loggers"]:
                        qlib_cfg = lc["loggers"]["qlib"]
                        if "handlers" in qlib_cfg:
                            qlib_cfg["handlers"] = []
                        qlib_cfg["propagate"] = True

            disable_qlib_file_logging(C.__dict__.get("_config", {}))
            disable_qlib_file_logging(C.__dict__.get("_default_config", {}))
            
            qlib_logger = logging.getLogger("qlib")
            qlib_logger.propagate = True
            for h in qlib_logger.handlers[:]:
                qlib_logger.removeHandler(h)
        except (ImportError, AttributeError):
            pass
        
        try:
            if hasattr(sys, 'argv') and sys.argv:
                cmd_line = " ".join(sys.argv)
                logger.debug(f"Command line: {cmd_line}")
        except Exception:
            pass

        _initialized_pid = current_pid

    return logger

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance with an optional name."""
    if name:
        return logging.getLogger(name)
    return logging.getLogger()

# Auto-initialize on import
#setup_logging()

def addHeader(logger: logging.Logger, title: str):
    """Add a visual header to the log."""
    pid = os.getpid()
    logger.info(f"\n{'='*20} START {title} (PID: {pid}) {'='*20}")

def addFooter(logger: logging.Logger, title: str):
    """Add a visual footer to the log."""
    pid = os.getpid()
    logger.info(f"{'='*20} END {title} (PID: {pid}) {'='*20}\n")

def startlog(name: str, **kwargs):
    """Initialize logging and print header. Wraps setup_logging."""
    logger = setup_logging(name=name, **kwargs)
    addHeader(logger, name)
    return logger

def endlog(logger: logging.Logger, name: str):
    """Print footer."""
    addFooter(logger, name)


if __name__ == "__main__":
    logger = startlog(f'logger_test')