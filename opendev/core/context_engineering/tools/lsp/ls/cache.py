from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class CacheMixin:
    """Mixin providing raw/processed symbol cache and pickle persistence."""

    def _save_raw_document_symbols_cache(self) -> None:
        from opendev.core.context_engineering.tools.lsp.util.cache import save_cache

        cache_file = self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._raw_document_symbols_cache_is_modified:
            log.debug("No changes to raw document symbols cache, skipping save")
            return

        log.info("Saving updated raw document symbols cache to %s", cache_file)
        try:
            save_cache(
                str(cache_file),
                self._raw_document_symbols_cache_version(),
                self._raw_document_symbols_cache,
            )
            self._raw_document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save raw document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def _raw_document_symbols_cache_version(self) -> tuple[int, Hashable]:
        return (
            self.RAW_DOCUMENT_SYMBOLS_CACHE_VERSION,
            self._ls_specific_raw_document_symbols_cache_version,
        )

    def _load_raw_document_symbols_cache(self) -> None:
        from opendev.core.context_engineering.tools.lsp.util.cache import load_cache
        from opendev.core.context_engineering.tools.lsp.util.compat import load_pickle

        cache_file = self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME

        if not cache_file.exists():
            # check for legacy cache to load to migrate
            legacy_cache_file = (
                self.cache_dir / self.RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK
            )
            if legacy_cache_file.exists():
                try:
                    legacy_cache: dict[str, tuple[str, tuple[list, list]]] = load_pickle(
                        legacy_cache_file
                    )
                    log.info(
                        "Migrating legacy document symbols cache with %d entries", len(legacy_cache)
                    )
                    num_symbols_migrated = 0
                    migrated_cache = {}
                    for cache_key, (file_hash, (all_symbols, root_symbols)) in legacy_cache.items():
                        if cache_key.endswith("-True"):  # include_body=True
                            new_cache_key = cache_key[:-5]
                            migrated_cache[new_cache_key] = (file_hash, root_symbols)
                            num_symbols_migrated += len(all_symbols)
                    log.info("Migrated %d document symbols from legacy cache", num_symbols_migrated)
                    self._raw_document_symbols_cache = migrated_cache  # type: ignore
                    self._raw_document_symbols_cache_is_modified = True
                    self._save_raw_document_symbols_cache()
                    legacy_cache_file.unlink()
                    return
                except Exception as e:
                    log.error("Error during cache migration: %s", e)
                    return

        # load existing cache (if any)
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                from opendev.core.context_engineering.tools.lsp.util.cache import load_cache

                saved_cache = load_cache(
                    str(cache_file), self._raw_document_symbols_cache_version()
                )
                if saved_cache is not None:
                    self._raw_document_symbols_cache = saved_cache
                    log.info(
                        f"Loaded {len(self._raw_document_symbols_cache)} entries from raw document symbols cache."
                    )
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load raw document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )

    def _save_document_symbols_cache(self) -> None:
        from opendev.core.context_engineering.tools.lsp.util.cache import save_cache

        cache_file = self.cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME

        if not self._document_symbols_cache_is_modified:
            log.debug("No changes to document symbols cache, skipping save")
            return

        log.info("Saving updated document symbols cache to %s", cache_file)
        try:
            save_cache(
                str(cache_file), self.DOCUMENT_SYMBOL_CACHE_VERSION, self._document_symbols_cache
            )
            self._document_symbols_cache_is_modified = False
        except Exception as e:
            log.error(
                "Failed to save document symbols cache to %s: %s. Note: this may have resulted in a corrupted cache file.",
                cache_file,
                e,
            )

    def _load_document_symbols_cache(self) -> None:
        from opendev.core.context_engineering.tools.lsp.util.cache import load_cache

        cache_file = self.cache_dir / self.DOCUMENT_SYMBOL_CACHE_FILENAME
        if cache_file.exists():
            log.info("Loading document symbols cache from %s", cache_file)
            try:
                saved_cache = load_cache(str(cache_file), self.DOCUMENT_SYMBOL_CACHE_VERSION)
                if saved_cache is not None:
                    self._document_symbols_cache = saved_cache
                    log.info(
                        f"Loaded {len(self._document_symbols_cache)} entries from document symbols cache."
                    )
            except Exception as e:
                # cache can become corrupt, so just skip loading it
                log.warning(
                    "Failed to load document symbols cache from %s (%s); Ignoring cache.",
                    cache_file,
                    e,
                )

    def save_cache(self) -> None:
        self._save_raw_document_symbols_cache()
        self._save_document_symbols_cache()
