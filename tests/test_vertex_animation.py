"""Offline tests for the vertex animation texture layout that game shaders read."""

import struct
import unittest
import zlib

import numpy as np
from yello_ext import vertex_animation


def random_normals(count: int) -> np.ndarray:
    vectors = np.random.default_rng(0).standard_normal((count, 3))
    axes = np.concatenate((np.eye(3), -np.eye(3)))
    vectors = np.concatenate((vectors, axes))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


class TestPackRows(unittest.TestCase):
    def test_shader_finds_each_vertex_on_every_frame(self):
        frame_count = 3
        vertex_count = vertex_animation.MAX_TEXTURE_WIDTH + 5
        vectors = np.arange(frame_count * vertex_count * 3, dtype=np.float32)
        vectors = vectors.reshape(frame_count, vertex_count, 3)
        pixels = vertex_animation.pack_rows(vectors)
        height, width, _ = pixels.shape
        rows_per_frame = height // frame_count
        texels = vertex_animation.get_vertex_texels(vertex_count)
        for vertex in (0, width - 1, width, vertex_count - 1):
            column, row = texels[vertex]
            for frame in range(frame_count):
                np.testing.assert_array_equal(
                    pixels[row + frame * rows_per_frame, column, :3],
                    vectors[frame, vertex],
                )

    def test_vertices_wrap_past_the_maximum_width(self):
        texels = vertex_animation.get_vertex_texels(
            vertex_animation.MAX_TEXTURE_WIDTH + 1
        )
        self.assertEqual(texels[-1].tolist(), [0, 1])


class TestPackTextures(unittest.TestCase):
    def setUp(self):
        self.positions = np.arange(2 * 4 * 3, dtype=np.float32).reshape(2, 4, 3)
        self.normals = random_normals(2)[:8].reshape(2, 4, 3)

    def test_packed_in_alpha_keeps_the_size_of_positions(self):
        texture, normal_map = vertex_animation.pack_textures(
            self.positions, self.normals, vertex_animation.NORMALS_PACKED_IN_ALPHA
        )
        self.assertEqual(texture.shape, (2, 4, 4))
        self.assertIsNone(normal_map)
        decoded = vertex_animation.decode_octahedral(texture[..., 3])
        self.assertLess(np.abs(decoded - self.normals).max(), 1e-3)

    def test_bottom_half_puts_normals_under_positions(self):
        texture, _ = vertex_animation.pack_textures(
            self.positions, self.normals, vertex_animation.NORMALS_BOTTOM_HALF
        )
        self.assertEqual(texture.shape, (4, 4, 4))
        np.testing.assert_array_equal(texture[3, :, :3], self.normals[1])

    def test_separate_file_maps_normals_into_zero_to_one(self):
        texture, normal_map = vertex_animation.pack_textures(
            self.positions, self.normals, vertex_animation.NORMALS_SEPARATE_FILE
        )
        self.assertEqual(texture.shape, (2, 4, 4))
        np.testing.assert_allclose(normal_map[1, :, :3] * 2.0 - 1.0, self.normals[1])

    def test_none_leaves_alpha_at_one(self):
        texture, normal_map = vertex_animation.pack_textures(
            self.positions, self.normals, vertex_animation.NORMALS_NONE
        )
        self.assertIsNone(normal_map)
        self.assertTrue(np.all(texture[..., 3] == 1.0))


class TestOctahedral(unittest.TestCase):
    def test_round_trip_stays_within_a_tenth_of_a_degree(self):
        normals = random_normals(10000)
        decoded = vertex_animation.decode_octahedral(
            vertex_animation.encode_octahedral(normals)
        )
        cosines = np.clip((decoded * normals).sum(axis=1), -1.0, 1.0)
        self.assertLess(np.degrees(np.arccos(cosines)).max(), 0.1)

    def test_packs_whole_numbers_a_float_holds_exactly(self):
        packed = vertex_animation.encode_octahedral(random_normals(10000))
        self.assertTrue(np.all(packed == np.floor(packed)))
        self.assertLess(packed.max(), 2**24)


class TestEncodePng(unittest.TestCase):
    def test_rows_decode_to_the_given_values(self):
        pixels = np.random.default_rng(1).random((3, 5, 4))
        data = vertex_animation.encode_png(pixels)
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (5, 3))
        length = struct.unpack(">I", data[33:37])[0]
        rows = np.frombuffer(zlib.decompress(data[41 : 41 + length]), dtype=np.uint8)
        rows = rows.reshape(3, 1 + 5 * 4)
        self.assertTrue(np.all(rows[:, 0] == 0))
        expected = np.rint(pixels * 255.0).reshape(3, -1)
        np.testing.assert_array_equal(rows[:, 1:], expected)


class TestToYUp(unittest.TestCase):
    def test_matches_the_gltf_exporter(self):
        vectors = vertex_animation.to_y_up(np.array([1.0, 2.0, 3.0]))
        self.assertEqual(vectors.tolist(), [1.0, 3.0, -2.0])
