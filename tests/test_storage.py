"""Persistence behavior that must hold for an empty GitHub checkout."""

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from dictionary_app.storage import DictionaryStore, Entry, get_app_data_dir


class DictionaryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.db_path = Path(self.temporary_directory.name) / "private" / "dictionary.sqlite3"
        self.store = DictionaryStore(self.db_path)

    def test_new_database_is_empty_and_persists_outside_checkout(self) -> None:
        self.assertEqual(self.store.list_entries(), [])
        self.assertEqual(self.store.search_entries("anything"), [])
        saved = self.store.upsert_entry(
            Entry(title="Erebus", original_input="厄瑞波斯", category="Mythology")
        )
        reopened = DictionaryStore(self.db_path)
        self.assertEqual(reopened.get_entry(saved.id), saved)
        self.assertEqual(reopened.list_entries(), [saved])

    def test_catalog_search_edit_and_delete(self) -> None:
        zebra = self.store.upsert_entry(Entry(title="Zebra", category="Animals"))
        ant = self.store.upsert_entry(Entry(title="Ant", category="Animals"))
        erebus = self.store.upsert_entry(
            Entry(title="Erebus", original_input="厄瑞波斯", category="Mythology",
                  subcategory="Greek", body_html="<p>Primordial darkness</p>")
        )
        self.assertEqual(
            [entry.title for entry in self.store.list_entries()],
            ["Ant", "Zebra", "Erebus"],
        )
        self.assertEqual(
            [entry.title for entry in self.store.list_entries(category="animals", limit=1, offset=1)],
            ["Zebra"],
        )
        self.assertEqual(self.store.search_entries("厄瑞"), [erebus])
        self.assertEqual(self.store.search_entries("Primordial"), [erebus])
        self.assertEqual(self.store.search_entries("%"), [])
        edited = self.store.upsert_entry(replace(erebus, body_html="<p>Greek deity</p>"))
        self.assertEqual(edited.created_at, erebus.created_at)
        self.assertEqual(self.store.get_entry(erebus.id), edited)
        self.assertTrue(self.store.delete_entry(ant.id))
        self.assertFalse(self.store.delete_entry(ant.id))
        self.assertIsNone(self.store.get_entry(ant.id))
        self.assertEqual(self.store.get_entry(zebra.id), zebra)
        with self.assertRaises(KeyError):
            self.store.upsert_entry(replace(ant, title="Ghost"))

    def test_images_have_stable_order_and_cascade_with_entry(self) -> None:
        entry = self.store.upsert_entry(Entry(title="Erebus"))
        first = self.store.add_image(entry.id, self.store.images_dir / "first.jpg",
                                     source_url="https://example.com/first",
                                     attribution="Artist", license="CC BY 4.0")
        second = self.store.add_image(entry.id, self.store.images_dir / "second.jpg",
                                      caption="A second depiction")
        early = self.store.add_image(entry.id, self.store.images_dir / "early.jpg",
                                     sort_order=-1)
        self.assertEqual(self.store.list_images(entry.id), [early, first, second])
        self.assertEqual(first.attribution, "Artist")
        self.assertEqual(second.sort_order, first.sort_order + 1)
        self.assertTrue(self.store.delete_image(first.id))
        self.assertFalse(self.store.delete_image(first.id))
        self.assertTrue(self.store.delete_entry(entry.id))
        self.assertEqual(self.store.list_images(entry.id), [])
        with self.assertRaises(KeyError):
            self.store.add_image(entry.id, "orphan.jpg")

    def test_windows_default_uses_user_local_app_data(self) -> None:
        with mock.patch("dictionary_app.storage.sys.platform", "win32"), \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": self.temporary_directory.name}):
            root = get_app_data_dir()
            self.assertEqual(root, Path(self.temporary_directory.name) / "PersonalDictionary")
            store = DictionaryStore()
            self.assertEqual(store.db_path.parent, root)
            self.assertEqual(store.list_entries(), [])


if __name__ == "__main__":
    unittest.main()
