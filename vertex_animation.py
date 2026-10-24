import struct
import zlib

import numpy as np

# WebGPU's guaranteed maximum texture dimension.
MAX_TEXTURE_WIDTH = 8192

NORMALS_PACKED_IN_ALPHA = "PACKED_IN_ALPHA"
NORMALS_BOTTOM_HALF = "BOTTOM_HALF"
NORMALS_SEPARATE_FILE = "SEPARATE_FILE"
NORMALS_NONE = "NONE"

# Two 12 bit axes make a whole number below 2^24, which a 32 bit float holds exactly.
OCTAHEDRAL_STEPS = 4095
OCTAHEDRAL_BASE = 4096


def get_texture_layout(vertex_count: int) -> tuple[int, int]:
    """Return the texture width and the number of rows each frame takes."""
    width = min(vertex_count, MAX_TEXTURE_WIDTH)
    rows_per_frame = -(-vertex_count // width)
    return width, rows_per_frame


def get_vertex_texels(vertex_count: int) -> np.ndarray:
    """Return the column and row of each vertex on the first frame."""
    width, _ = get_texture_layout(vertex_count)
    indices = np.arange(vertex_count)
    return np.stack((indices % width, indices // width), axis=1)


def to_y_up(vectors: np.ndarray) -> np.ndarray:
    """Convert Blender's Z up vectors to glTF's Y up, as the glTF exporter does."""
    return np.stack((vectors[..., 0], vectors[..., 2], -vectors[..., 1]), axis=-1)


def encode_octahedral(normals: np.ndarray) -> np.ndarray:
    """Return unit normals folded onto an octahedron as whole numbers below 2^24."""
    sums = np.maximum(np.abs(normals).sum(axis=-1, keepdims=True), 1e-12)
    x, y, z = np.moveaxis(normals / sums, -1, 0)
    folded = z < 0.0
    u = np.where(folded, (1.0 - np.abs(y)) * np.where(x >= 0.0, 1.0, -1.0), x)
    v = np.where(folded, (1.0 - np.abs(x)) * np.where(y >= 0.0, 1.0, -1.0), y)
    quantized_u = np.rint((u * 0.5 + 0.5) * OCTAHEDRAL_STEPS)
    quantized_v = np.rint((v * 0.5 + 0.5) * OCTAHEDRAL_STEPS)
    return (quantized_u * OCTAHEDRAL_BASE + quantized_v).astype(np.float32)


def decode_octahedral(packed: np.ndarray) -> np.ndarray:
    """Return the unit normals of encode_octahedral the way a game shader decodes them."""
    whole = packed.astype(np.uint32)
    u = (whole // OCTAHEDRAL_BASE) / OCTAHEDRAL_STEPS * 2.0 - 1.0
    v = (whole % OCTAHEDRAL_BASE) / OCTAHEDRAL_STEPS * 2.0 - 1.0
    z = 1.0 - np.abs(u) - np.abs(v)
    unfold = np.maximum(-z, 0.0)
    u = u + np.where(u >= 0.0, -unfold, unfold)
    v = v + np.where(v >= 0.0, -unfold, unfold)
    normals = np.stack((u, v, z), axis=-1)
    return normals / np.linalg.norm(normals, axis=-1, keepdims=True)


def pack_rows(vectors: np.ndarray, alpha: np.ndarray | None = None) -> np.ndarray:
    """Return top down RGBA rows holding each frame's vectors in turn, alpha 1 unless given."""
    frame_count, vertex_count, _ = vectors.shape
    width, rows_per_frame = get_texture_layout(vertex_count)
    pixels = np.zeros((frame_count * rows_per_frame, width, 4), dtype=np.float32)
    pixels[..., 3] = 1.0
    columns, rows = get_vertex_texels(vertex_count).T
    for frame in range(frame_count):
        frame_rows = rows + frame * rows_per_frame
        pixels[frame_rows, columns, :3] = vectors[frame]
        if alpha is not None:
            pixels[frame_rows, columns, 3] = alpha[frame]
    return pixels


def pack_textures(
    positions: np.ndarray, normals: np.ndarray, method: str
) -> tuple[np.ndarray, np.ndarray | None]:
    """Return the EXR's rows and, when normals get a file of their own, its rows."""
    if method == NORMALS_PACKED_IN_ALPHA:
        return pack_rows(positions, encode_octahedral(normals)), None
    if method == NORMALS_BOTTOM_HALF:
        return np.concatenate((pack_rows(positions), pack_rows(normals))), None
    if method == NORMALS_SEPARATE_FILE:
        return pack_rows(positions), pack_rows(normals * 0.5 + 0.5)
    return pack_rows(positions), None


def encode_png(pixels: np.ndarray) -> bytes:
    """Return an 8 bit RGBA PNG of top down rows of values from 0 to 1."""
    height, width, _ = pixels.shape
    values = np.rint(np.clip(pixels, 0.0, 1.0) * 255.0).astype(np.uint8)
    # Each row starts with a filter type byte, 0 for none.
    rows = np.concatenate(
        (np.zeros((height, 1), dtype=np.uint8), values.reshape(height, -1)), axis=1
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload)
    return (
        struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)
    )
