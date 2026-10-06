"""工程文件（.rld，JSON 明文）读写：原子写入 + 结构校验。"""
from __future__ import annotations

import json
import os

from core import registry
from core.model import Document
from graphics.items.base import LayoutItem
from graphics.scene import LayoutScene

FORMAT_NAME = "rail-layout"
FORMAT_VERSION = 1
FILE_SUFFIX = ".rld"
FILE_FILTER = "配线图工程 (*.rld);;JSON 文件 (*.json);;所有文件 (*.*)"


class ProjectFileError(Exception):
    """工程文件读写失败；消息面向用户，包含原因与下一步。"""


def document_to_dict(document: Document, scene: LayoutScene) -> dict:
    document.touch()
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "document": document.settings_dict(),
        "elements": [item.to_dict() for item in scene.layout_items()],
    }


def save_project(path: str, document: Document, scene: LayoutScene) -> None:
    payload = document_to_dict(document, scene)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError as error:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise ProjectFileError(
            f"无法写入文件：{error}\n"
            "请检查目标目录是否存在、是否有写入权限（或该文件正被其他程序占用）。"
        ) from error


def load_project(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as error:
        raise ProjectFileError("文件不存在或已被移动；请确认路径后重试，或从最近打开中移除。") from error
    except json.JSONDecodeError as error:
        raise ProjectFileError(
            f"文件内容不是有效 JSON（第 {error.lineno} 行附近），可能已损坏；"
            "请检查文件，或使用自动恢复快照。"
        ) from error
    except OSError as error:
        raise ProjectFileError(f"无法读取文件：{error}\n请检查文件权限后重试。") from error
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise ProjectFileError("该文件不是配线图工程文件（缺少 format 标记）；请确认选择的是 .rld 文件。")
    version = int(data.get("version", 0) or 0)
    if version > FORMAT_VERSION:
        raise ProjectFileError(
            f"文件由更高版本（v{version}）创建，当前程序最高支持 v{FORMAT_VERSION}；请升级程序后再打开。"
        )
    return data


def build_items(data: dict) -> list[LayoutItem]:
    items: list[LayoutItem] = []
    for index, element in enumerate(data.get("elements") or []):
        if not isinstance(element, dict):
            continue
        try:
            items.append(registry.create_element(element))
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectFileError(
                f"第 {index + 1} 个元素无法解析（{error}）；文件可能已损坏或来自不同版本。"
            ) from error
    return items


def apply_document_settings(document: Document, data: dict) -> None:
    document.apply_settings_dict(data.get("document") or {})
