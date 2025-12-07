"""
Unit tests for Key String Generator - Redis Cluster Hash Tag Support

Redis Cluster requires hash tags {content} to determine slot routing.
All keys for the same subsection should use the same hash tag to be co-located.

Hash Tag Strategy:
- Subsection-level keys: {e:EVENT_ID:ss:SECTION-SUBSECTION} - Same subsection in same slot
- Event-level keys: {e:EVENT_ID} - Event-wide keys in same slot
"""

import importlib
import os


class TestKeyStrGeneratorHashTags:
    """Test hash tag format for Redis Cluster compatibility"""

    def setup_method(self) -> None:
        """Clear any test prefix and reload module before each test"""
        os.environ.pop('KVROCKS_KEY_PREFIX', None)
        # Reload module to pick up cleared prefix
        from src.service.reservation.driven_adapter.reservation_helper import (
            key_str_generator,
        )

        importlib.reload(key_str_generator)

    # =========================================================================
    # Subsection-Level Keys - Hash Tag {e:EVENT_ID:ss:SECTION-SUBSECTION}
    # =========================================================================

    def test_seats_bf_key_has_subsection_hash_tag(self) -> None:
        """seats_bf key should have subsection-level hash tag for cluster routing"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_seats_bf_key,
        )

        key = make_seats_bf_key(event_id=1, section='A', subsection=1)

        # Hash tag should be {e:1:ss:A-1}
        assert key.startswith('{e:1:ss:A-1}')
        assert ':seats_bf' in key

    def test_seats_bf_key_different_subsections_different_tags(self) -> None:
        """Different subsections should have different hash tags"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_seats_bf_key,
        )

        key_a1 = make_seats_bf_key(event_id=1, section='A', subsection=1)
        key_b2 = make_seats_bf_key(event_id=1, section='B', subsection=2)

        # Extract hash tags
        tag_a1 = key_a1.split('}')[0] + '}'
        tag_b2 = key_b2.split('}')[0] + '}'

        assert tag_a1 == '{e:1:ss:A-1}'
        assert tag_b2 == '{e:1:ss:B-2}'
        assert tag_a1 != tag_b2

    def test_booking_key_has_subsection_hash_tag(self) -> None:
        """booking key should have subsection-level hash tag for co-location with seats_bf"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_booking_key,
        )

        key = make_booking_key(
            booking_id='019af799-ec16-73b2-b160-d24ae18b5942',
            event_id=1,
            section='A',
            subsection=1,
        )

        # Hash tag should be {e:1:ss:A-1}
        assert key.startswith('{e:1:ss:A-1}')
        assert ':booking:' in key
        assert '019af799-ec16-73b2-b160-d24ae18b5942' in key

    # =========================================================================
    # Event-Level Keys - Hash Tag {e:EVENT_ID}
    # =========================================================================

    def test_event_state_key_has_event_hash_tag(self) -> None:
        """event_state key should have event-level hash tag"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_event_state_key,
        )

        key = make_event_state_key(event_id=1)

        # Hash tag should be {e:1}
        assert key.startswith('{e:1}')
        assert ':event_state' in key

    def test_sellout_timer_key_has_event_hash_tag(self) -> None:
        """sellout_timer key should have event-level hash tag"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_sellout_timer_key,
        )

        key = make_sellout_timer_key(event_id=1)

        # Hash tag should be {e:1}
        assert key.startswith('{e:1}')
        assert ':sellout_timer' in key

    # =========================================================================
    # Co-location Tests - Keys that need to be in same slot
    # =========================================================================

    def test_seats_and_booking_same_hash_tag(self) -> None:
        """seats_bf and booking for same subsection should have same hash tag"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_booking_key,
            make_seats_bf_key,
        )

        seats_key = make_seats_bf_key(event_id=1, section='A', subsection=1)
        booking_key = make_booking_key(
            booking_id='test-booking-id',
            event_id=1,
            section='A',
            subsection=1,
        )

        # Both should have same hash tag {e:1:ss:A-1}
        seats_tag = seats_key.split('}')[0] + '}'
        booking_tag = booking_key.split('}')[0] + '}'

        assert seats_tag == booking_tag == '{e:1:ss:A-1}'

    def test_event_level_keys_same_hash_tag(self) -> None:
        """event_state and sellout_timer should have same hash tag"""
        from src.service.reservation.driven_adapter.reservation_helper.key_str_generator import (
            make_event_state_key,
            make_sellout_timer_key,
        )

        event_state_key = make_event_state_key(event_id=1)
        sellout_key = make_sellout_timer_key(event_id=1)

        event_tag = event_state_key.split('}')[0] + '}'
        sellout_tag = sellout_key.split('}')[0] + '}'

        assert event_tag == sellout_tag == '{e:1}'

    # =========================================================================
    # Test Prefix Support (for test isolation)
    # =========================================================================

    def test_key_prefix_applied_after_hash_tag(self) -> None:
        """Key prefix for test isolation should be applied after hash tag"""
        os.environ['KVROCKS_KEY_PREFIX'] = 'test123:'

        # Re-import to pick up new prefix
        import importlib

        from src.service.reservation.driven_adapter.reservation_helper import (
            key_str_generator,
        )

        importlib.reload(key_str_generator)

        key = key_str_generator.make_seats_bf_key(event_id=1, section='A', subsection=1)

        # Prefix should be before hash tag
        assert key.startswith('test123:{e:1:ss:A-1}')

        # Cleanup
        os.environ.pop('KVROCKS_KEY_PREFIX', None)
        importlib.reload(key_str_generator)
