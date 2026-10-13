import sys
import pytest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestFeatureColumns:

    def test_feature_columns_defined(self):
        from analytics.models.anomaly_detector import FEATURE_COLUMNS
        assert isinstance(FEATURE_COLUMNS, list)
        assert len(FEATURE_COLUMNS) >= 5, "Expect at least 5 meaningful features"
        assert all(isinstance(f, str) for f in FEATURE_COLUMNS)

    def test_no_ground_truth_in_features(self):
        from analytics.models.anomaly_detector import FEATURE_COLUMNS
        leakage_cols = {"is_anomaly", "ground_truth", "anomaly_type",
                        "fraud_label", "label"}
        for col in FEATURE_COLUMNS:
            assert col not in leakage_cols, f"DATA LEAKAGE: '{col}' in FEATURE_COLUMNS"

    def test_expected_features_present(self):
        from analytics.models.anomaly_detector import FEATURE_COLUMNS
        expected = {"log_amount", "hour_of_day", "amount_zscore"}
        for f in expected:
            assert f in FEATURE_COLUMNS, f"Expected feature '{f}' missing"


class TestStatisticalBaseline:

    def test_baseline_flags_high_zscore(self):
        import pandas as pd
        from analytics.models.anomaly_detector import statistical_baseline

        df = pd.DataFrame({
            "amount_zscore": [0.5, 1.0, -0.3, 4.5, 10.0, 0.1]
        })
        flags = statistical_baseline(df, threshold_sigma=3.0)
        # Only z-scores 4.5 and 10.0 exceed 3.0
        assert flags[0] == 0  # normal
        assert flags[3] == 1  # 4.5 sigma
        assert flags[4] == 1  # 10.0 sigma

    def test_baseline_returns_binary(self):
        import pandas as pd
        from analytics.models.anomaly_detector import statistical_baseline

        df = pd.DataFrame({"amount_zscore": np.random.randn(100)})
        flags = statistical_baseline(df)
        unique = set(flags)
        assert unique.issubset({0, 1}), f"Non-binary values: {unique}"


class TestEngineerFeatures:

    def test_amount_zscore_computed(self):
        import pandas as pd
        from analytics.models.anomaly_detector import engineer_features

        df = pd.DataFrame({
            "amount":             [100.0],
            "customer_avg_amount": [100.0],
            "customer_std_amount": [20.0],
            "hour_of_day":         [14],
            "day_of_week":         [1],
            "customer_txn_count":  [50],
        })
        result = engineer_features(df)
        assert result["amount_zscore"].iloc[0] == pytest.approx(0.0, abs=1e-9)

    def test_night_flag_set_correctly(self):
        import pandas as pd
        from analytics.models.anomaly_detector import engineer_features

        df = pd.DataFrame({
            "amount":             [100.0, 100.0, 100.0],
            "customer_avg_amount": [100.0, 100.0, 100.0],
            "customer_std_amount": [20.0,  20.0,  20.0],
            "hour_of_day":         [2,     14,     23],    # night, day, night
            "day_of_week":         [1,     1,      1],
            "customer_txn_count":  [50,    50,     50],
        })
        result = engineer_features(df)
        assert result["is_night_txn"].iloc[0] == 1   # 2am → night
        assert result["is_night_txn"].iloc[1] == 0   # 2pm → day
        assert result["is_night_txn"].iloc[2] == 1   # 11pm → night

    def test_log_customer_txn_count_positive(self):
        import pandas as pd
        from analytics.models.anomaly_detector import engineer_features

        df = pd.DataFrame({
            "amount":             [50.0] * 5,
            "customer_avg_amount": [50.0] * 5,
            "customer_std_amount": [10.0] * 5,
            "hour_of_day":         [10] * 5,
            "day_of_week":         [2] * 5,
            "customer_txn_count":  [1, 5, 10, 100, 1000],
        })
        result = engineer_features(df)
        assert all(result["log_customer_txn_count"] >= 0)


class TestModelReproducibility:

    def test_same_seed_same_flags(self):
        import pandas as pd
        from analytics.models.anomaly_detector import (
            engineer_features, train_and_score, FEATURE_COLUMNS
        )

        # Small synthetic dataframe (no DB needed)
        np.random.seed(42)
        n = 200
        base_df = pd.DataFrame({
            "transaction_id":      range(n),
            "txn_timestamp":       pd.date_range("2023-01-01", periods=n, freq="h"),
            "amount":              np.abs(np.random.normal(100, 30, n)),
            "ground_truth":        ([0] * 190) + ([1] * 10),
            "log_amount":          np.log1p(np.abs(np.random.normal(100, 30, n))),
            "hour_of_day":         np.random.randint(0, 24, n),
            "day_of_week":         np.random.randint(0, 7, n),
            "merchant_risk_encoded": np.random.randint(0, 3, n),
            "channel_encoded":     np.random.randint(0, 5, n),
            "customer_avg_amount": np.full(n, 100.0),
            "customer_std_amount": np.full(n, 20.0),
            "customer_txn_count":  np.full(n, 50),
        })

        df1 = engineer_features(base_df.copy())
        df2 = engineer_features(base_df.copy())

        scored1, _, _, _ = train_and_score(df1, contamination=0.05, random_seed=42)
        scored2, _, _, _ = train_and_score(df2, contamination=0.05, random_seed=42)

        assert (scored1["is_flagged"].values == scored2["is_flagged"].values).all(), \
            "Isolation Forest must produce identical flags with same seed"
