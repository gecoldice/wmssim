"""DEV-15 复杂识图/场地：失败与校正路径。不写入正式几何。"""

from __future__ import annotations

from typing import Any, Dict, Optional

RECOGNITION_CAPABILITIES = (
    "dxf_vector_extract",
    "ocr_assist",
    "polygon_height_partition",
)

_DXF_TYPES = {"application/dxf", "image/vnd.dxf", "application/acad", "application/dwg"}
_DXF_EXTS = (".dxf", ".dwg")


def _failure(code: str, message: str, *, action: str, correction: str) -> Dict[str, Any]:
    return {
        "failure": {"code": code, "message": message},
        "correction": {
            "action": action,
            "message": correction,
            "dropsSource": False,
        },
    }


def _base(capability: str, drawing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "capability": capability,
        "implemented": False,
        "status": "unsupported",
        "claimsValidatedGeometry": False,
        "producedGeometry": None,
        "producedFacility": None,
        "preciseRackLayout": None,
        "drawingRetained": drawing is not None,
        "confirmationStatus": "pending",
        "engineVersion": "m5-extend-0.1",
    }


def _is_dxf(source: Dict[str, Any]) -> bool:
    media = str(source.get("mediaType") or "").lower()
    name = str(source.get("filename") or "").lower()
    if media in _DXF_TYPES or "dxf" in media or media.endswith("dwg"):
        return True
    return name.endswith(_DXF_EXTS)


def _scale_declared(source: Dict[str, Any]) -> bool:
    if source.get("scaleDeclared") is True:
        return True
    mpp = source.get("metersPerPixel")
    return isinstance(mpp, (int, float)) and float(mpp) > 0


def _is_complex_site(source: Dict[str, Any]) -> bool:
    if source.get("concave") is True or source.get("nonRect") is True:
        return True
    if source.get("coldStorage") is True or source.get("hazmat") is True:
        return True
    floors = source.get("floors")
    if isinstance(floors, (int, float)) and float(floors) > 1:
        return True
    zones = source.get("heightZones")
    if isinstance(zones, (int, float)) and float(zones) > 1:
        return True
    return False


def assess_recognition(
    *,
    capability: str,
    source: Optional[Dict[str, Any]] = None,
    drawing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估一种识图能力。永远不返回已验证几何。

    调用方传入的多边形、轮廓或 OCR 文本会被忽略，不能当成场地确认。
    """
    src = dict(source or {})
    # 丢弃调用方自带的几何，避免把未实现提取伪装成结果。
    src.pop("polygons", None)
    src.pop("contours", None)
    src.pop("extractedGeometry", None)

    result = _base(capability, drawing)
    if capability not in RECOGNITION_CAPABILITIES:
        result["status"] = "failed"
        result.update(
            _failure(
                "UNKNOWN_RECOGNITION_CAPABILITY",
                f"不支持的识图能力：{capability}",
                action="choose_supported_or_trace",
                correction="改用人工描边确认场地，或只选择已登记的识图入口（它们目前都会失败并保留底图）。",
            )
        )
        return result

    filename = src.get("filename") or (drawing or {}).get("filename")
    if capability == "dxf_vector_extract":
        if not filename:
            result["status"] = "failed"
            result.update(
                _failure(
                    "MISSING_SOURCE",
                    "没有 DXF/DWG 文件，无法提取矢量。",
                    action="upload_or_trace",
                    correction="上传图纸或改用人工描边。未上传的文件不会被丢弃，因为本来就没有文件。",
                )
            )
            return result
        if not _is_dxf(src) and not str(filename).lower().endswith(_DXF_EXTS):
            result["status"] = "failed"
            result.update(
                _failure(
                    "SOURCE_TYPE_MISMATCH",
                    "矢量提取只接受 DXF/DWG。当前文件类型不能当成矢量场地。",
                    action="upload_dxf_or_trace",
                    correction="换 DXF/DWG，或在底图上人工描边。底图元数据保留，不升为已确认几何。",
                )
            )
            return result
        result["status"] = "unsupported"
        result.update(
            _failure(
                "DXF_EXTRACT_UNSUPPORTED",
                "已登记 DXF/矢量提取，但本切片没有矢量解析器，不能输出轮廓、柱或门。",
                action="manual_trace",
                correction="保留底图，改用人工描边并标定比例。不要把文件里的图元当成已验证场地。",
            )
        )
        return result

    if capability == "ocr_assist":
        if not filename:
            result["status"] = "failed"
            result.update(
                _failure(
                    "MISSING_SOURCE",
                    "没有图片或 PDF 页，无法做 OCR 辅助。",
                    action="upload_or_trace",
                    correction="上传底图后人工核对文字，或直接描边。OCR 未运行。",
                )
            )
            return result
        confidence = src.get("ocrConfidence")
        result["status"] = "needs_confirmation"
        result["ocrConfidenceEcho"] = confidence if isinstance(confidence, (int, float)) else None
        result.update(
            _failure(
                "OCR_NOT_VERIFIED",
                "OCR 辅助未实现。即便调用方给出高置信度，也不能把文字当成工程条件已验证。",
                action="confirm_pending",
                correction="识别结果保持「待确认」。请人工核对比例、边界、门和净高后再确认场地。",
            )
        )
        return result

    # polygon_height_partition
    if not _scale_declared(src):
        result["status"] = "failed"
        result.update(
            _failure(
                "SCALE_MISSING",
                "缺少比例（metersPerPixel 或 scaleDeclared）。不能生成精确货架或分区。",
                action="declare_scale",
                correction="先标定一条已知长度，或改为手工输入米制场地。未标定图纸不得进入 validated 布局。",
            )
        )
        return result
    if _is_complex_site(src):
        result["status"] = "unsupported"
        result.update(
            _failure(
                "SITE_COMPLEXITY_UNSUPPORTED",
                "凹多边形、多层、多净高分区、冷库或危化不在本切片自动分区范围内。",
                action="manual_trace",
                correction="保留底图，改用人工描边确认净轮廓、障碍、门和净高。系统不会自动切出高度分区。",
            )
        )
        return result
    result["status"] = "unsupported"
    result.update(
        _failure(
            "POLYGON_PARTITION_UNSUPPORTED",
            "即便是已标定的简单矩形，本切片也不做自动多边形/高度分区。",
            action="manual_facility",
            correction="在工作台手工输入米制边界与障碍。自动分区没有结果，不能当成已确认场地。",
        )
    )
    return result
