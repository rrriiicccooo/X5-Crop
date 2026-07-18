from __future__ import annotations

import inspect
import unittest

from x5crop.image import evidence as image_evidence
from x5crop.detection.physical import frame_sequence_solver


class ContentEvidenceArchitectureContractTest(unittest.TestCase):
    def test_content_evidence_has_no_configurable_component_reducer(self) -> None:
        self.assertFalse(hasattr(image_evidence, "ContentEvidenceImageParameters"))
        self.assertFalse(hasattr(image_evidence, "_three_component_consensus"))

    def test_global_tonal_position_is_not_content_evidence(self) -> None:
        source = inspect.getsource(image_evidence.make_content_evidence_gray)
        self.assertNotIn("tonal_presence", source)

    def test_content_evidence_does_not_allocate_a_partition_stack(self) -> None:
        source = inspect.getsource(image_evidence.make_content_evidence_gray)

        self.assertNotIn("np.stack", source)
        self.assertNotIn("np.partition", source)

    def test_content_never_upgrades_frame_boundary_roles(self) -> None:
        source = inspect.getsource(frame_sequence_solver)

        self.assertNotIn("_support_content_boundary_role", source)
        self.assertNotIn("_corroborate_external_content_boundary_roles", source)
        self.assertNotIn("content_boundary_role", source)


if __name__ == "__main__":
    unittest.main()
