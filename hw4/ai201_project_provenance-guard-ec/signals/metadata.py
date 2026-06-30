"""
signals/metadata.py — Metadata classifier (rule-based, pure Python).

Part of the Multi-modal Support stretch feature.

Extends detection beyond free text to structured metadata describing a
piece of media (modeled on image metadata, e.g. EXIF-style fields). This
is NOT pixel-level image analysis — it is a rule-based check of fields
that commonly accompany an upload: which software produced the file,
what camera (if any) captured it, and whether expected camera fields
are present or conspicuously absent.

Expected input shape
─────────────────────
{
    "camera_model":   "Canon EOS R5"   | None,
    "software_used":  "Adobe Lightroom" | "Midjourney v6" | None,
    "creation_tool":  "Photoshop"       | "DALL-E 3"       | None,
    "iso":            400               | None,
    "aperture":       "f/2.8"           | None,
}
All fields are optional; missing fields are treated as absent evidence,
not as positive evidence of either class.
"""

# Known AI image/content generation tool signatures.
_AI_TOOL_SIGNATURES = frozenset([
    "midjourney", "dall-e", "dalle", "stable diffusion", "adobe firefly",
    "firefly", "runway", "leonardo.ai", "leonardo ai", "ideogram",
    "imagen", "flux", "sora",
])

# Camera / photo-editing software signatures (evidence of human/camera origin).
_CAMERA_SOFTWARE_SIGNATURES = frozenset([
    "adobe lightroom", "adobe photoshop", "capture one", "darktable",
    "vsco", "snapseed", "gimp",
])

# Fields a genuine camera-captured photo would typically populate.
_CAMERA_FIELDS = ("camera_model", "iso", "aperture")


def classify_metadata(metadata: dict) -> dict:
    """
    Classify a piece of content based on structured metadata alone.

    Parameters
    ----------
    metadata : dict with optional keys camera_model, software_used,
               creation_tool, iso, aperture (see module docstring)

    Returns
    -------
    {
        "signal": "metadata",
        "score":  float,   # 0.0 (human/camera-likely) – 1.0 (AI-likely)
        "components": {
            "ai_tool_signature_found": bool,
            "camera_software_found":   bool,
            "camera_fields_present":   int,    # 0-3
        }
    }
    """
    metadata = metadata or {}

    software_used  = str(metadata.get("software_used") or "").lower()
    creation_tool  = str(metadata.get("creation_tool") or "").lower()
    combined_tool_text = f"{software_used} {creation_tool}"

    ai_tool_found = any(sig in combined_tool_text for sig in _AI_TOOL_SIGNATURES)
    camera_sw_found = any(sig in combined_tool_text for sig in _CAMERA_SOFTWARE_SIGNATURES)

    camera_fields_present = sum(
        1 for field in _CAMERA_FIELDS
        if metadata.get(field) not in (None, "", 0)
    )

    # ── Scoring logic ────────────────────────────────────────────────────────
    # Direct tool signature is the strongest evidence in either direction.
    if ai_tool_found:
        score = 0.95
    elif camera_sw_found and camera_fields_present >= 2:
        score = 0.05
    elif camera_fields_present >= 2:
        # Camera fields present but no recognized software — likely a real photo
        score = 0.15
    elif camera_fields_present == 0 and not software_used and not creation_tool:
        # No evidence at all — genuinely uncertain, not leaning either way
        score = 0.50
    elif camera_fields_present == 0:
        # Software/tool mentioned but unrecognized, and no camera fields —
        # mild lean toward AI-generated, since real photos usually retain
        # at least some camera metadata even after editing
        score = 0.65
    else:
        score = 0.50

    return {
        "signal": "metadata",
        "score": round(score, 4),
        "components": {
            "ai_tool_signature_found": ai_tool_found,
            "camera_software_found":   camera_sw_found,
            "camera_fields_present":   camera_fields_present,
        },
    }
