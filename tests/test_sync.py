from unittest.mock import MagicMock

from sync import fetch_activity_details


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
