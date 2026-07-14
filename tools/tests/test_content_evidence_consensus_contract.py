from __future__ import annotations

import inspect
import unittest

import numpy as np

from x5crop.image import evidence as image_evidence


class ContentEvidenceConsensusContractTest(unittest.TestCase):
    def test_three_component_consensus_matches_exact_order_statistics(self) -> None:
        consensus = getattr(image_evidence, "_three_component_consensus", None)
        self.assertIsNotNone(consensus)
        components = np.random.default_rng(7).random(
            (3, 17, 23),
            dtype=np.float32,
        )

        for minimum_channels in range(1, 4):
            expected = np.partition(
                components,
                -minimum_channels,
                axis=0,
            )[-minimum_channels]
            actual = consensus(tuple(components), minimum_channels)
            np.testing.assert_array_equal(actual, expected)

    def test_global_tonal_position_is_not_content_evidence(self) -> None:
        self.assertNotIn(
            "tonal_presence_percentile",
            image_evidence.ContentEvidenceImageParameters.__dataclass_fields__,
        )
        source = inspect.getsource(image_evidence.make_content_evidence_gray)
        self.assertNotIn("tonal_presence", source)

    def test_content_evidence_does_not_allocate_a_partition_stack(self) -> None:
        source = inspect.getsource(image_evidence.make_content_evidence_gray)

        self.assertNotIn("np.stack", source)
        self.assertNotIn("np.partition", source)


if __name__ == "__main__":
    unittest.main()
