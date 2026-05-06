"""
file_executor.py — Real file system operations for the builder.

All writes go to: config.BUILDER_PROJECTS_DIR / project_name /
DRY_RUN mode prints intent only — no disk mutations.
"""

import logging
from pathlib import Path

from core.config import config

logger = logging.getLogger("presence.builder.file_executor")


def _resolve(project_root: Path, relative_path: str) -> Path:
    """Resolve a relative path inside the project root. Blocks path traversal."""
    target = (project_root / relative_path).resolve()
    if not str(target).startswith(str(project_root.resolve())):
        raise ValueError(f"[BUILDER] Path traversal blocked: {relative_path!r}")
    return target


def create_file(project_root: Path, relative_path: str, content: str) -> Path:
    """
    Write content to a new file inside project_root.
    Creates parent directories as needed.
    In DRY_RUN mode: logs intent, skips disk write.
    Returns the resolved Path.
    """
    target = _resolve(project_root, relative_path)
    if config.BUILDER_DRY_RUN:
        logger.info(f"[DRY-RUN] Would create file: {target}  ({len(content)} chars)")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info(f"[BUILDER] File created → {target}")
    return target


def update_file(project_root: Path, relative_path: str, content: str) -> Path:
    """
    Overwrite an existing file inside project_root.
    In DRY_RUN mode: logs intent, skips disk write.
    Returns the resolved Path.
    """
    target = _resolve(project_root, relative_path)
    if config.BUILDER_DRY_RUN:
        logger.info(f"[DRY-RUN] Would update file: {target}  ({len(content)} chars)")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info(f"[BUILDER] File updated → {target}")
    return target


def read_file(project_root: Path, relative_path: str) -> str:
    """
    Read a file from project_root. Raises FileNotFoundError with [ERROR] log on miss.
    """
    target = _resolve(project_root, relative_path)
    if not target.exists():
        logger.error(f"[ERROR] File not found: {target}")
        raise FileNotFoundError(f"File not found: {target}")
    content = target.read_text(encoding="utf-8")
    logger.debug(f"[BUILDER] File read → {target}  ({len(content)} chars)")
    return content


def create_project_dir(project_name: str) -> Path:
    """
    Create and return the root directory for a project.
    If a project with this name already exists, appends a numeric suffix (_2, _3, ...).
    In DRY_RUN mode: returns path without creating it.
    """
    base = config.BUILDER_PROJECTS_DIR / project_name
    root = base

    # Collision detection — find a unique name
    suffix = 1
    while root.exists() and any(root.iterdir()):
        suffix += 1
        root = config.BUILDER_PROJECTS_DIR / f"{project_name}_{suffix}"

    if root != base:
        logger.info(f"[BUILDER] Folder collision detected >> using {root.name} (suffix _{suffix})")
    else:
        logger.info(f"[BUILDER] No collision >> {root.name}")

    if config.BUILDER_DRY_RUN:
        logger.info(f"[DRY-RUN] Would create project directory: {root}")
        return root

    root.mkdir(parents=True, exist_ok=True)
    logger.info(f"[BUILDER] Project directory ready >> {root}")
    return root


def create_subdirs(project_root: Path, folders: list[str]) -> None:
    """Create all subdirectories listed in the plan's folder_structure."""
    for folder in folders:
        if folder in (".", ""):
            continue
        target = _resolve(project_root, folder)
        if config.BUILDER_DRY_RUN:
            logger.info(f"[DRY-RUN] Would create dir: {target}")
            continue
        target.mkdir(parents=True, exist_ok=True)
        logger.info(f"[BUILDER] Dir created → {target}")
