from unittest.mock import MagicMock

from sync import fetch_activity_details, sync_performance_metrics


def test_fetch_details_calls_splits_for_activity_with_distance():
    client = MagicMock()
    summary = {"activityType": {"typeKey": "trail_running"}, "distance": 5000}
    fetch_activity_details(client, "123", summary)
    client.get_activity_splits.assert_called_once_with("123")


def test_fetch_details_calls_exercise_sets_for_activity_with_sets():
    client = MagicMock()
    summary = {"activityType": {"typeKey": "strength_training"}, "totalSets": 10}
    fetch_activity_details(client, "123", summary)
    client.get_activity_exercise_sets.assert_called_once_with("123")


def test_fetch_details_no_splits_for_no_distance():
    client = MagicMock()
    summary = {"activityType": {"typeKey": "yoga"}, "duration": 3600}
    fetch_activity_details(client, "123", summary)
    client.get_activity_splits.assert_not_called()


def test_fetch_details_no_exercise_sets_for_no_sets():
    client = MagicMock()
    summary = {"activityType": {"typeKey": "running"}, "distance": 5000}
    fetch_activity_details(client, "123", summary)
    client.get_activity_exercise_sets.assert_not_called()


def test_sync_performance_metrics_saves_file(tmp_path):
    client = MagicMock()
    client.get_max_metrics_latest.return_value = {"generic": [{"vo2MaxPreciseValue": 42.5}]}
    client.get_training_status.return_value = {"currentTrainingStatus": "PRODUCTIVE"}
    client.get_race_predictions.return_value = [{"raceTime": {"5k": 1500}}]
    client.get_endurance_score.return_value = {"overallScore": 68}
    client.get_lactate_threshold.return_value = {"lactateThreshold": 170}
    client.get_training_four_week_load_balance.return_value = {"weeklyTrainingLoads": []}

    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    result = sync_performance_metrics(client, "2026-11-25", stats_dir)
    assert "max_metrics" in result
    assert (stats_dir / "performance.json").exists()


def test_sync_performance_metrics_handles_failures(tmp_path):
    client = MagicMock()
    client.get_max_metrics_latest.side_effect = Exception("not available")
    client.get_training_status.side_effect = Exception("not available")
    client.get_race_predictions.side_effect = Exception("not available")
    client.get_endurance_score.side_effect = Exception("not available")
    client.get_lactate_threshold.side_effect = Exception("not available")
    client.get_training_four_week_load_balance.side_effect = Exception("not available")

    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    result = sync_performance_metrics(client, "2026-11-25", stats_dir)
    assert result == {}
    assert not (stats_dir / "performance.json").exists()
