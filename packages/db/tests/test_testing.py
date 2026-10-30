from agentic_db.testing import session_database


def test_each_test_session_gets_a_database_of_its_own() -> None:
    """Two sessions on one Postgres must never drop or empty each other's database."""
    first, drop_first = session_database("arp", {})
    second, drop_second = session_database("arp", {})
    assert first != second
    assert first.startswith("arp_test_") and second.startswith("arp_test_")
    assert drop_first and drop_second  # throwaway: dropped when the session ends
    assert len(first) <= 63  # a Postgres identifier


def test_a_named_test_database_is_kept() -> None:
    assert session_database("arp", {"ARP_TEST_DB_NAME": "arp_test_api"}) == ("arp_test_api", False)
