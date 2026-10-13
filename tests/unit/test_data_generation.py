import sys
import random
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDeterminism:

    def test_random_date_deterministic(self):
        from datetime import date
        import random as _random
        import numpy as _np

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        _random.seed(42)
        _np.random.seed(42)

        from scripts.generate_data import random_date, START_DATE, END_DATE
        dates1 = [random_date(START_DATE, END_DATE) for _ in range(10)]

        _random.seed(42)
        _np.random.seed(42)
        dates2 = [random_date(START_DATE, END_DATE) for _ in range(10)]

        assert dates1 == dates2, "random_date() must be deterministic with same seed"

    def test_normal_amount_always_positive(self):
        import random as _random
        import numpy as _np
        from scripts.generate_data import normal_amount

        _random.seed(42)
        _np.random.seed(42)

        for segment in ["retail", "premium", "business", "vip"]:
            amounts = [normal_amount(segment) for _ in range(100)]
            assert all(a > 0 for a in amounts), f"Negative amount found for segment {segment}"

    def test_normal_amount_respects_segment_scale(self):
        import random as _random
        import numpy as _np
        from scripts.generate_data import normal_amount

        _random.seed(42)
        _np.random.seed(42)

        retail_avg  = sum(normal_amount("retail")  for _ in range(200)) / 200
        vip_avg     = sum(normal_amount("vip")     for _ in range(200)) / 200

        assert vip_avg > retail_avg * 5, "VIP spend should be at least 5x retail"


class TestAnomalyInjection:

    def test_anomaly_type_constants_exist(self):
        import scripts.generate_data as gd
        expected_types = {
            "large_amount", "velocity_burst", "unusual_hour",
            "foreign_high_risk", "pattern_shift"
        }

        source = Path(gd.__file__).read_text()
        for t in expected_types:
            assert t in source, f"Anomaly type '{t}' not found in generator source"

    def test_feature_columns_no_leakage(self):
        """The ML feature list must NOT include ground truth label columns."""
        from analytics.models.anomaly_detector import FEATURE_COLUMNS
        forbidden = {"is_anomaly", "ground_truth", "anomaly_type"}
        overlap = forbidden.intersection(set(FEATURE_COLUMNS))
        assert not overlap, f"Data leakage: {overlap} found in FEATURE_COLUMNS"


class TestWeightedChoice:

    def test_output_always_in_options(self):
        from scripts.generate_data import weighted_choice
        options = ["a", "b", "c"]
        weights = [1, 2, 3]
        for _ in range(100):
            result = weighted_choice(options, weights)
            assert result in options

    def test_weights_influence_distribution(self):
        from scripts.generate_data import weighted_choice
        counts = {"a": 0, "b": 0, "c": 0}
        for _ in range(1000):
            r = weighted_choice(["a", "b", "c"], [1, 1, 100])
            counts[r] += 1
        assert counts["c"] > counts["a"] * 5
        assert counts["c"] > counts["b"] * 5
