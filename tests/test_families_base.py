"""Unit tests for the ChipFamily registry (families/base.py).

Covers the ADR-0001 contract: auto-registration on subclass definition,
id-collision detection, the missing-family_ids guard, and get()'s
None/raise semantics.
"""

import pytest

from families.base import ChipFamily


class _Sample(ChipFamily):
    family_ids = ("sample21", "sample51")

    def required_packages(self, board):
        return {}

    def build_flags(self, board):
        return []

    def upload_protocol(self, board):
        return "swd"

    def inject_debug_tools(self, board):
        pass

    def configure_debug_session(self, debug_config):
        pass

    def build_script(self, env, board):
        return "frameworks/_bare.py"

    def arduino_script(self, env, board):
        return "../board_build/_bare/_bare.py"


class TestRegistration:
    def test_subclass_registers_all_ids(self):
        assert ChipFamily.get("sample21").__class__ is _Sample
        assert ChipFamily.get("sample51").__class__ is _Sample

    def test_known_family_ids_sorted(self):
        ids = ChipFamily.known_family_ids()
        assert "sample21" in ids and "sample51" in ids
        assert list(ids) == sorted(ids)

    def test_duplicate_id_rejected(self):
        with pytest.raises(TypeError, match="already registered"):

            class _Clash(ChipFamily):
                family_ids = ("sample21",)

                def required_packages(self, board):
                    return {}

                def build_flags(self, board):
                    return []

                def upload_protocol(self, board):
                    return "swd"

                def inject_debug_tools(self, board):
                    pass

                def configure_debug_session(self, debug_config):
                    pass

    def test_concrete_family_without_ids_not_caught_at_class_creation(self):
        # __init_subclass__ runs before ABCMeta computes __abstractmethods__,
        # so the missing-ids guard cannot fire there (see base.py comment).
        # Such a class simply registers nothing; the verify_boards gate
        # catches it post-creation. This test pins that semantics.

        class _NoIds(ChipFamily):
            def required_packages(self, board):
                return {}

            def build_flags(self, board):
                return []

            def upload_protocol(self, board):
                return "swd"

            def inject_debug_tools(self, board):
                pass

            def configure_debug_session(self, debug_config):
                pass

        assert not any(v is _NoIds for v in ChipFamily._registry.values())
        # ...and ChipFamily.get can never resolve it:
        with pytest.raises(KeyError):
            ChipFamily.get("whatever")

    def test_abstract_intermediate_allows_empty_ids(self):
        # An intermediate base with remaining abstract methods and empty
        # ids must register nothing and raise nothing.
        class _Group(ChipFamily):
            family_ids = ()

        assert not any(v is _Group for v in ChipFamily._registry.values())


class TestGet:
    def test_none_returns_none(self):
        assert ChipFamily.get(None) is None
        assert ChipFamily.get("") is None

    def test_unknown_raises_with_vocabulary(self):
        with pytest.raises(KeyError, match="unknown chip family 'ghost'"):
            ChipFamily.get("ghost")

    def test_get_returns_instance(self):
        fam = ChipFamily.get("sample21")
        assert isinstance(fam, _Sample)
        assert fam.upload_protocol({}) == "swd"
