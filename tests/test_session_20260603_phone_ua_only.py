"""Tests for Ukrainian-only phone number filter."""

from telegram.handlers.contact.user_phone_number import _is_ukrainian_phone


class TestUkrainianPhoneFilter:
    def test_plus_380_accepted(self):
        assert _is_ukrainian_phone("+380671234567") is True

    def test_380_without_plus_accepted(self):
        assert _is_ukrainian_phone("380671234567") is True

    def test_russian_plus_7_rejected(self):
        assert _is_ukrainian_phone("+79161234567") is False

    def test_poland_plus_48_rejected(self):
        assert _is_ukrainian_phone("+48571234567") is False

    def test_usa_plus_1_rejected(self):
        assert _is_ukrainian_phone("+12025551234") is False

    def test_germany_plus_49_rejected(self):
        assert _is_ukrainian_phone("+491701234567") is False

    def test_empty_rejected(self):
        assert _is_ukrainian_phone("") is False

    def test_none_rejected(self):
        assert _is_ukrainian_phone(None) is False

    def test_short_ua_number_rejected(self):
        assert _is_ukrainian_phone("+38067123") is False

    def test_too_long_rejected(self):
        assert _is_ukrainian_phone("+3806712345678") is False

    def test_38_without_zero_rejected(self):
        # +38 без 0 после — не украинский формат
        assert _is_ukrainian_phone("+38671234567") is False
